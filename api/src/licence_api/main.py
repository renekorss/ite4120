"""Versioned React-facing API; sessions, authorization and persistence stay server-side."""

import base64
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

from licence_api import models as m
from licence_api.authentication import PasswordAuthentication
from licence_api.config import Settings
from licence_api.store import (
    ISSUER,
    Store,
    assess_medical,
    audit,
    cancel_obsolete,
    lock_user,
    medical_observation,
    utcnow,
)
from licence_api.upstream import XRoadClient

MESSAGES = json.loads((Path(__file__).parent / "locales/et.json").read_text())
ENGLISH = json.loads((Path(__file__).parent / "locales/en.json").read_text())
LANGUAGE = ContextVar("language", default="et")
AUTH = HTTPBearer(auto_error=False)
LOG = logging.getLogger("licence_api")
ERRORS = {401: "AUTH_REQUIRED", 403: "AUTH_REQUIRED", 404: "NOT_FOUND", 422: "VALIDATION_ERROR"}


def message(code):
    """Render only application-owned text, never upstream error strings."""
    messages = ENGLISH if LANGUAGE.get() == "en" else MESSAGES
    return messages.get(code, messages["CHECK_STATUS_DESCRIPTION"])


def error_response(status, code, trace_id, fields=None):
    return JSONResponse(
        status_code=status,
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
        content={
            "error": {
                "code": code,
                "message": message(code),
                "traceId": str(trace_id),
                "fields": fields or [],
            }
        },
    )


def check_view(row, latest_id):
    """Translate a persisted check into a minimized, user-scoped public result."""
    return m.Check(
        id=row["id"],
        requested_at=row["requested_at"],
        completed_at=row["completed_at"],
        outcome=row["outcome"],
        outcome_label=message("OUTCOME_" + row["outcome"].upper()),
        driving_status=row["driving_status"],
        status_changed=row["status_changed"],
        error=m.Message(code=row["error_code"], message=message(row["error_code"]))
        if row["error_code"]
        else None,
        is_latest_successful=row["id"] == latest_id,
        source=row["source_code"],
        source_label=message("SOURCE_LABEL"),
    )


def driving_data(conn, user_id, settings):
    """Present mixed-age cache observations explicitly instead of fabricating fresh data."""
    latest = conn.execute(
        "SELECT * FROM latest_successful_check WHERE user_id=%s", (user_id,)
    ).fetchone()
    recent = conn.execute(
        """SELECT * FROM status_check WHERE user_id=%s
           ORDER BY requested_at DESC,id DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    updated = latest["completed_at"] if latest else None
    latest_id = latest["id"] if latest else None
    stale = not updated or (utcnow() - updated).total_seconds() > settings.stale_seconds
    stale = stale or bool(recent and recent["outcome"] == "failed")
    licences = []
    # Invalid source results omit licence details; retain the older document cache
    # for display with isCurrent=false and its own original cachedAt timestamp.
    rows = conn.execute(
        """SELECT d.*,c.completed_at FROM driving_licence d JOIN status_check c ON c.id=d.check_id
           WHERE c.user_id=%s AND d.check_id=(SELECT sc.id FROM status_check sc
             WHERE sc.user_id=%s AND sc.outcome='successful' AND EXISTS (
               SELECT 1 FROM driving_licence x WHERE x.check_id=sc.id)
             ORDER BY sc.completed_at DESC,sc.id DESC LIMIT 1)
           ORDER BY d.id""",
        (user_id, user_id),
    ).fetchall()
    deadlines = []
    for row in rows:
        current = row["check_id"] == latest_id
        categories = conn.execute(
            "SELECT * FROM licence_category WHERE licence_id=%s ORDER BY category_code",
            (row["id"],),
        ).fetchall()
        licences.append(
            m.Licence(
                id=row["id"],
                status=row["document_status"],
                issued_on=row["issued_on"],
                expires_on=row["expires_on"],
                expiry_kind=row["expiry_kind"],
                categories=[
                    m.Category(
                        code=c["category_code"],
                        first_issued_on=c["first_issued_on"],
                        expires_on=c["expires_on"],
                    )
                    for c in categories
                ],
                cached_at=row["completed_at"],
                is_current=current,
            )
        )
        if current:
            deadlines.extend(
                (d, stale) for d in [row["expires_on"], *(c["expires_on"] for c in categories)] if d
            )
    certificates = []
    requirement, medical_rows = medical_observation(conn, user_id)
    for row in medical_rows:
        current = row["check_id"] == latest_id
        certificates.append(
            m.MedicalCertificate(
                id=row["id"],
                status=row["certificate_status"],
                issued_on=row["issued_on"],
                expires_on=row["expires_on"],
                cached_at=row["completed_at"],
                is_current=current,
            )
        )
        if row["expires_on"]:
            deadlines.append((row["expires_on"], not current or stale))
    warnings = [
        m.Message(code="MEDICAL_DATA_UNAVAILABLE", message=message("MEDICAL_DATA_UNAVAILABLE"))
    ]
    if settings.medical_path and medical_rows and medical_rows[0]["check_id"] == latest_id:
        warnings.clear()
    if stale:
        warnings.append(m.Message(code="STALE_DATA", message=message("STALE_DATA")))
    if any(licence.expiry_kind == "driving_right" for licence in licences):
        warnings.append(
            m.Message(code="DRIVING_RIGHT_DEADLINE", message=message("DRIVING_RIGHT_DEADLINE"))
        )
    status = latest["driving_status"] if latest else "unknown"
    reason = latest["reason_code"] if latest else None
    current_dates = [
        d
        for licence in licences
        if licence.is_current
        for d in [licence.expires_on, *(c.expires_on for c in licence.categories)]
        if d
    ]
    if status != "invalid" and current_dates:
        days_left = (min(current_dates) - utcnow().date()).days
        if days_left < 0:
            status, reason = "invalid", "LICENCE_EXPIRED"
        elif days_left <= settings.risk_days:
            status, reason = "at_risk", "EXPIRY_APPROACHING"
    status, reason = assess_medical(status, reason, requirement, medical_rows, settings.risk_days)
    next_date = min((item[0] for item in deadlines), default=None)
    cutoff = utcnow().date() + timedelta(days=settings.risk_days)
    renewal_actions = []
    if any(d <= cutoff for d in current_dates) or any(
        licence.expires_on and licence.expires_on <= cutoff for licence in licences
    ):
        renewal_actions.append("renew_licence")
    if any(med.expires_on and med.expires_on <= cutoff for med in certificates):
        renewal_actions.append("renew_medical")
    return m.DrivingData(
        renewal_actions=renewal_actions,
        status=status,
        status_label=message("STATUS_" + status.upper()),
        reason_codes=[reason] if reason else [],
        explanations=[message(reason)] if reason else [],
        last_updated_at=updated,
        latest_check=check_view(recent, latest_id) if recent else None,
        is_stale=stale,
        medical_requirement=requirement,
        licences=licences,
        medical_certificates=certificates,
        next_expiry_date=next_date,
        next_expiry_is_stale=any(flag for value, flag in deadlines if value == next_date),
        warnings=warnings,
    )


def preferences(conn, user_id):
    row = conn.execute("SELECT * FROM reminder_preference WHERE user_id=%s", (user_id,)).fetchone()
    intervals = conn.execute(
        "SELECT days_before FROM reminder_interval WHERE user_id=%s ORDER BY days_before DESC",
        (user_id,),
    ).fetchall()
    return m.Preferences(
        enabled=row["enabled"],
        intervals=[r["days_before"] for r in intervals],
        updated_at=row["updated_at"],
    )


class BodyLimit:
    """Limit decoded request size before JSON parsing, including chunked requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        content = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            content.extend(event.get("body", b""))
            if len(content) > 65536:
                response = error_response(
                    413, "PAYLOAD_TOO_LARGE", scope.get("state", {}).get("trace_id", uuid4())
                )
                return await response(scope, receive, send)
            if not event.get("more_body"):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(content), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


def create_app(settings=None):
    """Build the app with explicit settings and close pools/HTTP clients on shutdown."""
    settings = settings or Settings.from_env()
    from licence_api.delivery import public_key

    push_public_key = public_key(settings)
    cipher = Fernet(settings.push_key)
    passwords = PasswordAuthentication(settings)

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings)
        app.state.source = XRoadClient(settings)
        try:
            yield
        finally:
            app.state.source.close()
            app.state.store.close()

    app = FastAPI(
        title="Driving Licence Reminder API",
        version="1.0.0",
        lifespan=lifespan,
        description=(
            "React-facing API with password authentication; "
            "the configured X-Road data source is synthetic."
        ),
        responses={
            code: {"model": m.ErrorResponse} for code in (400, 401, 404, 409, 422, 429, 503)
        },
    )
    app.add_middleware(BodyLimit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        expose_headers=["X-Request-Id", "Retry-After"],
    )

    @app.middleware("http")
    async def request_context(request, call_next):
        LANGUAGE.set(
            "en" if request.headers.get("accept-language", "").lower().startswith("en") else "et"
        )
        request.state.trace_id = uuid4()
        try:
            response = await call_next(request)
        except Exception:
            request.state.error_code = "INTERNAL_ERROR"
            response = error_response(500, "INTERNAL_ERROR", request.state.trace_id)
        response.headers["X-Request-Id"] = str(request.state.trace_id)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        failed = response.status_code >= 400 or bool(getattr(request.state, "error_code", None))
        if settings.log_level in {"DEBUG", "INFO"} or failed:
            LOG.warning(
                json.dumps(
                    {
                        "@timestamp": utcnow().isoformat(),
                        "event": {
                            "action": "api.request",
                            "outcome": "failure" if failed else "success",
                        },
                        "trace": {"id": str(request.state.trace_id)},
                        "error": {"code": getattr(request.state, "error_code", None)},
                        "http": {
                            "request": {"method": request.method},
                            "response": {"status_code": response.status_code},
                        },
                    }
                )
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        request.state.error_code = "VALIDATION_ERROR"
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        return error_response(422, "VALIDATION_ERROR", request.state.trace_id, fields)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        code = (
            exc.detail
            if isinstance(exc.detail, str) and exc.detail in MESSAGES
            else ERRORS.get(exc.status_code, "INTERNAL_ERROR")
        )
        request.state.error_code = code
        response = error_response(exc.status_code, code, request.state.trace_id)
        if exc.status_code == 429:
            response.headers["Retry-After"] = (exc.headers or {}).get("Retry-After", "1")
        return response

    @app.exception_handler(psycopg.errors.LockNotAvailable)
    async def locked_error(request, _exc):
        request.state.error_code = "REFRESH_BUSY"
        return error_response(409, "REFRESH_BUSY", request.state.trace_id)

    @app.exception_handler(PoolTimeout)
    @app.exception_handler(psycopg.OperationalError)
    async def database_error(request, _exc):
        request.state.error_code = "DATABASE_UNAVAILABLE"
        return error_response(503, "DATABASE_UNAVAILABLE", request.state.trace_id)

    @app.exception_handler(Exception)
    async def internal_error(request, _exc):
        # Do not log exception text: database diagnostics and client errors may
        # contain credentials, bound values, upstream URLs or personal data.
        return error_response(500, "INTERNAL_ERROR", request.state.trace_id)

    def identity(
        request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(AUTH)
    ):
        token = (
            credentials.credentials
            if credentials and credentials.scheme.lower() == "bearer"
            else ""
        )
        with app.state.store.connection() as conn:
            row = None
            if 32 <= len(token) <= 256:
                row = conn.execute(
                    """SELECT s.id AS session_id,s.expires_at,s.revoked_at,
                       u.id,u.identity_subject,u.identity_issuer,u.deleted_at,c.display_name,c.is_enabled
                       FROM web_session s JOIN user_account u ON u.id=s.user_id
                       JOIN password_credential c ON c.user_id=u.id WHERE s.token_hash=%s""",
                    (hashlib.sha256(token.encode()).digest(),),
                ).fetchone()
            if (
                not row
                or not row["is_enabled"]
                or row["revoked_at"]
                or row["deleted_at"]
                or row["expires_at"] <= utcnow()
            ):
                audit(
                    conn,
                    "authorization.denied",
                    request.state.trace_id,
                    row["id"] if row else None,
                    "failure",
                    "AUTH_REQUIRED",
                )
                conn.commit()
                raise HTTPException(401, "AUTH_REQUIRED")
            return row

    @app.get("/health", response_model=m.Health, tags=["Operations"])
    def health():
        with app.state.store.connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/v1/config", response_model=m.FrontendConfig, tags=["Configuration"])
    def frontend_config():
        return {
            "authenticationMode": "demo_code" if settings.demo_login else "password",
            "availableIntervals": [90, 30, 7],
            "sessionWarningSeconds": settings.session_warning_seconds,
            "push": {"available": bool(push_public_key), "publicKey": push_public_key},
        }

    @app.post("/api/v1/auth/demo-login", response_model=m.SessionResponse, tags=["Authentication"])
    def demo_login(payload: m.DemoLogin, request: Request):
        if not settings.demo_login or settings.app_env not in {"development", "test"}:
            raise HTTPException(404, "NOT_FOUND")
        with app.state.store.connection() as conn:
            return passwords.demo_login(
                conn,
                payload.personal_code,
                request.client.host if request.client else "unknown",
                request.state.trace_id,
            )

    @app.post("/api/v1/auth/login", response_model=m.SessionResponse, tags=["Authentication"])
    def login(payload: m.LoginInput, request: Request):
        with app.state.store.connection() as conn:
            source_address = request.client.host if request.client else "unknown"
            return passwords.login(conn, payload, source_address, request.state.trace_id)

    @app.post("/api/v1/auth/logout", status_code=204, tags=["Authentication"])
    def logout(request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            conn.execute(
                "UPDATE web_session SET revoked_at=clock_timestamp() WHERE id=%s",
                (user["session_id"],),
            )
            audit(conn, "session.revoked", request.state.trace_id, user["id"])
        return Response(status_code=204)

    @app.get("/api/v1/me", response_model=m.Profile, tags=["Profile"])
    def profile(request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            audit(conn, "profile.viewed", request.state.trace_id, user["id"])
        return m.Profile(
            id=user["id"],
            display_name=user["display_name"],
            data_is_synthetic=user["identity_issuer"] == ISSUER,
            session_expires_at=user["expires_at"],
            session_warning_seconds=settings.session_warning_seconds,
        )

    @app.get("/api/v1/me/driving-data", response_model=m.DrivingData, tags=["Driving data"])
    def driving(request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            result = driving_data(conn, user["id"], settings)
            audit(conn, "driving_data.viewed", request.state.trace_id, user["id"])
            return result

    @app.post(
        "/api/v1/me/driving-data/refresh", response_model=m.RefreshResponse, tags=["Driving data"]
    )
    def refresh(request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            if not lock_user(conn, user["id"]):
                raise HTTPException(401, "AUTH_REQUIRED")
            check_id = app.state.store.refresh(
                conn,
                user["id"],
                user["identity_subject"],
                request.state.trace_id,
                app.state.source,
                settings,
            )
            row = conn.execute(
                "SELECT * FROM status_check WHERE id=%s AND user_id=%s", (check_id, user["id"])
            ).fetchone()
            data = driving_data(conn, user["id"], settings)
            request.state.error_code = row["error_code"]
            return m.RefreshResponse(
                check=check_view(row, check_id if row["outcome"] == "successful" else None),
                data=data,
            )

    @app.get("/api/v1/me/status-checks", response_model=m.CheckList, tags=["Driving data"])
    def checks(request: Request, limit: int = Query(5, ge=1, le=50), user=Depends(identity)):
        with app.state.store.connection() as conn:
            latest = conn.execute(
                "SELECT id FROM latest_successful_check WHERE user_id=%s", (user["id"],)
            ).fetchone()
            rows = conn.execute(
                """SELECT * FROM status_check WHERE user_id=%s
                   ORDER BY requested_at DESC,id DESC LIMIT %s""",
                (user["id"], limit + 1),
            ).fetchall()
            audit(conn, "status_checks.viewed", request.state.trace_id, user["id"])
            return m.CheckList(
                items=[check_view(row, latest["id"] if latest else None) for row in rows[:limit]],
                limit=limit,
                has_more=len(rows) > limit,
            )

    @app.get("/api/v1/me/status-checks/{check_id}", response_model=m.Check, tags=["Driving data"])
    def check(check_id: UUID, request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM status_check WHERE id=%s AND user_id=%s", (check_id, user["id"])
            ).fetchone()
            if not row:
                audit(
                    conn,
                    "authorization.denied",
                    request.state.trace_id,
                    user["id"],
                    "failure",
                    "NOT_FOUND",
                )
                conn.commit()
                raise HTTPException(404, "NOT_FOUND")
            latest = conn.execute(
                "SELECT id FROM latest_successful_check WHERE user_id=%s", (user["id"],)
            ).fetchone()
            audit(conn, "status_check.viewed", request.state.trace_id, user["id"])
            return check_view(row, latest["id"] if latest else None)

    @app.get("/api/v1/me/reminder-preferences", response_model=m.Preferences, tags=["Reminders"])
    def get_preferences(request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            result = preferences(conn, user["id"])
            audit(conn, "reminders.viewed", request.state.trace_id, user["id"])
            result.delivery_available = bool(push_public_key)
            return result

    @app.put("/api/v1/me/reminder-preferences", response_model=m.Preferences, tags=["Reminders"])
    def put_preferences(payload: m.PreferencesInput, request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            if not lock_user(conn, user["id"]):
                raise HTTPException(401, "AUTH_REQUIRED")
            conn.execute(
                """UPDATE reminder_preference SET enabled=%s,updated_at=clock_timestamp()
                   WHERE user_id=%s""",
                (payload.enabled, user["id"]),
            )
            conn.execute("DELETE FROM reminder_interval WHERE user_id=%s", (user["id"],))
            for days in payload.intervals:
                conn.execute(
                    "INSERT INTO reminder_interval(user_id,days_before) VALUES (%s,%s)",
                    (user["id"], days),
                )
            latest = conn.execute(
                "SELECT id FROM latest_successful_check WHERE user_id=%s", (user["id"],)
            ).fetchone()
            cancel_obsolete(conn, user["id"], latest["id"] if latest else None)
            audit(
                conn,
                "reminders.changed" if payload.enabled else "reminders.disabled",
                request.state.trace_id,
                user["id"],
            )
            result = preferences(conn, user["id"])
            result.delivery_available = bool(push_public_key)
            return result

    @app.get("/api/v1/me/notifications", response_model=m.NotificationList, tags=["Notifications"])
    def notifications(
        request: Request, limit: int = Query(20, ge=1, le=50), user=Depends(identity)
    ):
        with app.state.store.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM notification WHERE user_id=%s
                   AND state='sent' AND sent_at IS NOT NULL
                   ORDER BY sent_at DESC,id DESC LIMIT %s""",
                (user["id"], limit + 1),
            ).fetchall()
            audit(conn, "notifications.viewed", request.state.trace_id, user["id"])
            return m.NotificationList(
                items=[
                    m.Notification(
                        id=row["id"],
                        sent_at=row["sent_at"],
                        document_kind=row["document_kind"],
                        document_label=message(
                            "LICENCE_LABEL"
                            if row["document_kind"] == "driving_licence"
                            else "MEDICAL_LABEL"
                        ),
                        expires_on=row["expires_on"],
                        days_before=row["days_before"],
                        message=message(
                            "NOTIFICATION_LICENCE"
                            if row["document_kind"] == "driving_licence"
                            else "NOTIFICATION_MEDICAL"
                        ).format(date=row["expires_on"].strftime("%d.%m.%Y")),
                    )
                    for row in rows[:limit]
                ],
                limit=limit,
                has_more=len(rows) > limit,
            )

    @app.get("/api/v1/me/renewal-guidance", response_model=m.Guidance, tags=["Guidance"])
    def guidance(request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            data = driving_data(conn, user["id"], settings)
            codes = [action.upper() for action in data.renewal_actions] or ["CHECK_STATUS"]
            audit(conn, "renewal_guidance.viewed", request.state.trace_id, user["id"])
            return m.Guidance(
                actions=[
                    m.GuidanceAction(
                        code=code.lower(),
                        title=message(code + "_TITLE"),
                        description=message(code + "_DESCRIPTION"),
                        official_url=settings.official_renewal_url,
                    )
                    for code in codes
                ],
                external_notice=message("EXTERNAL_NOTICE"),
                fallback_message=message("EXTERNAL_FALLBACK"),
                official_url=settings.official_renewal_url,
            )

    @app.post(
        "/api/v1/me/push-subscriptions", response_model=m.Subscription, tags=["Notifications"]
    )
    def subscribe(payload: m.SubscriptionInput, request: Request, user=Depends(identity)):
        host = urlsplit(payload.endpoint)
        try:
            port = host.port
        except ValueError as exc:
            raise HTTPException(422, "PUSH_INVALID") from exc
        if not settings.push_hosts:
            raise HTTPException(409, "PUSH_NOT_CONFIGURED")
        if (
            host.scheme != "https"
            or host.hostname not in settings.push_hosts
            or port not in {None, 443}
            or host.username
            or host.password
            or host.fragment
        ):
            raise HTTPException(422, "PUSH_INVALID")
        try:
            public_key = base64.urlsafe_b64decode(
                payload.keys.p256dh + "=" * (-len(payload.keys.p256dh) % 4)
            )
            auth_key = base64.urlsafe_b64decode(
                payload.keys.auth + "=" * (-len(payload.keys.auth) % 4)
            )
            if len(public_key) != 65 or public_key[0] != 4 or len(auth_key) != 16:
                raise ValueError("Invalid subscription key lengths")
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_key)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "PUSH_INVALID") from exc
        encrypted = cipher.encrypt(payload.model_dump_json(by_alias=True).encode())
        fingerprint = hashlib.sha256(payload.endpoint.encode()).digest()
        with app.state.store.connection() as conn:
            if not lock_user(conn, user["id"]):
                raise HTTPException(401, "AUTH_REQUIRED")
            # One browser endpoint must never receive reminders from two demo users.
            conn.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (int.from_bytes(fingerprint[:8], "big", signed=True),),
            )
            conn.execute(
                """UPDATE web_push_subscription SET revoked_at=clock_timestamp()
                WHERE endpoint_hash=%s AND user_id<>%s AND revoked_at IS NULL""",
                (fingerprint, user["id"]),
            )
            row = conn.execute(
                """INSERT INTO web_push_subscription(
                   id,user_id,encrypted_subscription,encryption_key_ref,endpoint_hash)
                   VALUES (%s,%s,%s,'local-fernet-v1',%s) ON CONFLICT(user_id,endpoint_hash)
                   DO UPDATE SET encrypted_subscription=EXCLUDED.encrypted_subscription,
                   revoked_at=NULL
                   RETURNING id,created_at,revoked_at""",
                (uuid4(), user["id"], encrypted, fingerprint),
            ).fetchone()
            audit(conn, "push.registered", request.state.trace_id, user["id"])
            return m.Subscription(**row, delivery_available=bool(push_public_key))

    @app.delete(
        "/api/v1/me/push-subscriptions/{subscription_id}", status_code=204, tags=["Notifications"]
    )
    def unsubscribe(subscription_id: UUID, request: Request, user=Depends(identity)):
        with app.state.store.connection() as conn:
            if not lock_user(conn, user["id"]):
                raise HTTPException(401, "AUTH_REQUIRED")
            row = conn.execute(
                """UPDATE web_push_subscription
                   SET revoked_at=COALESCE(revoked_at,clock_timestamp())
                   WHERE id=%s AND user_id=%s RETURNING id""",
                (subscription_id, user["id"]),
            ).fetchone()
            if not row:
                audit(
                    conn,
                    "authorization.denied",
                    request.state.trace_id,
                    user["id"],
                    "failure",
                    "NOT_FOUND",
                )
                conn.commit()
                raise HTTPException(404, "NOT_FOUND")
            conn.execute(
                """UPDATE notification SET state='cancelled',claimed_until=NULL WHERE user_id=%s
                   AND subscription_id=%s AND state IN ('pending','processing','failed')""",
                (user["id"], subscription_id),
            )
            audit(conn, "push.revoked", request.state.trace_id, user["id"])
        return Response(status_code=204)

    return app
