"""Transactional PostgreSQL access using runtime privileges and bound SQL parameters."""

from datetime import datetime, timezone
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from licence_api.upstream import UpstreamError

ISSUER = "synthetic-driving-reminder-v1"
# Explicit test identity mapping; never accept a national ID from the frontend.
SYNTHETIC_PROFILES = {
    "valid": ("demo-valid", "00000000001", "Kehtiv juhiluba"),
    "expiring": ("demo-licence-90-days", "00000000002", "Aeguv juhiluba"),
    "medical": ("demo-medical-30-days", "00000000001", "Aeguv tervisetõend (salvestatud näide)"),
    "both": ("demo-both-7-days", "00000000002", "Mõlemad tähtajad lähenevad (salvestatud näide)"),
    "expired": ("demo-licence-expired", "00000000003", "Kehtetu juhiluba"),
    "invalid": ("demo-medical-expired", "00000000004", "Kehtetu juhtimisõigus"),
    "renewed": ("demo-renewed", "00000000001", "Uuendatud juhiluba (salvestatud näide)"),
    "unavailable": ("demo-unavailable", "00000000005", "Andmeallika tõrge"),
    "slow": ("demo-slow", "00000000006", "Aeglane andmeallikas"),
}


def utcnow():
    return datetime.now(timezone.utc)


# A licence-only refresh has no medical observation. Keep the most recent
# independent medical result, including a later explicit change in applicability.
LATEST_MEDICAL = """
    SELECT DISTINCT ON (c.user_id) c.id,c.user_id,c.medical_requirement,c.completed_at
    FROM status_check c WHERE c.outcome='successful' AND (
      c.medical_requirement IN ('required','not_required') OR EXISTS (
        SELECT 1 FROM medical_certificate m WHERE m.check_id=c.id))
    ORDER BY c.user_id,c.completed_at DESC,c.id DESC
"""


def medical_observation(conn, user_id):
    """Read the last medical assessment with its original observation timestamp."""
    check = conn.execute(
        "SELECT * FROM (" + LATEST_MEDICAL + ") medical WHERE user_id=%s", (user_id,)
    ).fetchone()
    if not check:
        return "unknown", []
    rows = conn.execute(
        """SELECT m.*,c.completed_at FROM medical_certificate m
          JOIN status_check c ON c.id=m.check_id WHERE m.check_id=%s ORDER BY m.id""",
        (check["id"],),
    ).fetchall()
    return check["medical_requirement"], rows


def assess_medical(status, reason, requirement, certificates, risk_days):
    """Combine the licence result with the saved required certificate deadline."""
    dates = [row["expires_on"] for row in certificates if row["expires_on"]]
    if requirement == "required" and dates and status != "invalid":
        days = (min(dates) - utcnow().date()).days
        if days < 0:
            return "invalid", "MEDICAL_EXPIRED"
        if days <= risk_days and status == "valid":
            return "at_risk", "MEDICAL_EXPIRY_APPROACHING"
    return status, reason


def audit(conn, action, trace_id, user_id=None, outcome="success", error_code=None):
    """Append minimized audit evidence in the same transaction as the local change."""
    conn.execute(
        """INSERT INTO audit_event(id, actor_user_id, subject_user_id, actor_kind,
           action_code, outcome, error_code, trace_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            uuid4(),
            user_id,
            user_id,
            "user" if user_id else "anonymous",
            action,
            outcome,
            error_code,
            trace_id,
        ),
    )


def lock_user(conn, user_id):
    """Serialize refresh and settings/route changes across API instances."""
    row = conn.execute(
        "SELECT id FROM user_account WHERE id=%s AND deleted_at IS NULL FOR UPDATE",
        (user_id,),
    ).fetchone()
    return row is not None


class Store:
    """A bounded, reusable runtime connection pool; never connects as database owner."""

    def __init__(self, settings):
        self.pool = ConnectionPool(
            kwargs={
                "host": settings.db_host,
                "port": settings.db_port,
                "dbname": settings.db_name,
                "user": settings.db_user,
                "password": settings.db_password,
                "connect_timeout": 3,
                "options": "-c timezone=UTC -c statement_timeout=10000 -c lock_timeout=2000",
                "row_factory": dict_row,
            },
            min_size=0,
            max_size=settings.pool_max,
            timeout=3,
            open=True,
            check=ConnectionPool.check_connection,
        )

    def close(self):
        self.pool.close()

    def connection(self):
        return self.pool.connection()

    def refresh(self, conn, user_id, subject, trace_id, client, settings):
        """Complete a serialized refresh atomically, retaining old snapshots on failure."""
        check_id = uuid4()
        previous = conn.execute(
            "SELECT * FROM latest_successful_check WHERE user_id=%s", (user_id,)
        ).fetchone()
        conn.execute(
            """INSERT INTO status_check(id,user_id,outcome,trace_id,xroad_request_id)
               VALUES (%s,%s,'pending',%s,%s)""",
            (check_id, user_id, trace_id, str(trace_id)),
        )
        try:
            scenario = next(
                (key for key, profile in SYNTHETIC_PROFILES.items() if profile[0] == subject), None
            )
            if scenario is None:
                raise UpstreamError("XR_IDENTITY_NOT_CONFIGURED")
            observation = client.fetch(SYNTHETIC_PROFILES[scenario][1], trace_id)
            medical_expiry = (
                client.fetch_medical(scenario, trace_id) if settings.medical_path else None
            )
        except UpstreamError as exc:
            conn.execute(
                """UPDATE status_check SET outcome='failed',completed_at=clock_timestamp(),
                   error_code=%s WHERE id=%s""",
                (exc.code, check_id),
            )
            audit(conn, "driving_data.refresh_failed", trace_id, user_id, "failure", exc.code)
            return check_id
        status, reason = observation.status, observation.reason
        if observation.expires_on:
            next_date = min(observation.expires_on, *(c[2] for c in observation.categories))
            days = (next_date - utcnow().date()).days
            if days < 0:
                status, reason = "invalid", "LICENCE_EXPIRED"
            elif days <= settings.risk_days:
                status, reason = "at_risk", "EXPIRY_APPROACHING"
        if medical_expiry:
            requirement, certificates = "required", [{"expires_on": medical_expiry}]
        else:
            requirement, certificates = medical_observation(conn, user_id)
        status, reason = assess_medical(
            status, reason, requirement, certificates, settings.risk_days
        )
        changed = previous["driving_status"] != status if previous else None
        conn.execute(
            """UPDATE status_check SET outcome='successful',completed_at=clock_timestamp(),
               driving_status=%s,reason_code=%s,medical_requirement=%s,status_changed=%s,
               xroad_request_id=%s WHERE id=%s""",
            (
                status,
                reason,
                "required" if medical_expiry else "unknown",
                changed,
                observation.request_id,
                check_id,
            ),
        )
        if observation.expires_on:
            licence_id = uuid4()
            conn.execute(
                """INSERT INTO driving_licence(
                   id,check_id,document_status,issued_on,expires_on,expiry_kind)
                   VALUES (%s,%s,%s,%s,%s,'driving_right')""",
                (
                    licence_id,
                    check_id,
                    "expired" if observation.expires_on < utcnow().date() else "valid",
                    observation.issued_on,
                    observation.expires_on,
                ),
            )
            for code, issued, end in observation.categories:
                conn.execute(
                    """INSERT INTO licence_category(
                       licence_id,category_code,first_issued_on,expires_on)
                       VALUES (%s,%s,%s,%s)""",
                    (licence_id, code, issued, end),
                )
        if medical_expiry:
            conn.execute(
                """INSERT INTO medical_certificate(id,check_id,certificate_status,expires_on)
                VALUES (%s,%s,%s,%s)""",
                (
                    uuid4(),
                    check_id,
                    "expired" if medical_expiry < utcnow().date() else "valid",
                    medical_expiry,
                ),
            )
        cancel_obsolete(conn, user_id, check_id)
        audit(conn, "driving_data.refresh_succeeded", trace_id, user_id)
        return check_id


def cancel_obsolete(conn, user_id, current_check_id):
    """Cancel unsent obsolete targets while preserving sent history and old snapshots."""
    conn.execute(
        """UPDATE notification n SET state='cancelled',claimed_until=NULL
           WHERE n.user_id=%s AND n.state IN ('pending','failed','processing') AND (
             NOT EXISTS (SELECT 1 FROM reminder_preference p
                         WHERE p.user_id=n.user_id AND p.enabled)
             OR NOT EXISTS (SELECT 1 FROM reminder_interval i WHERE i.user_id=n.user_id
                            AND i.days_before=n.days_before)
             OR (n.document_kind='driving_licence' AND NOT EXISTS (
                 SELECT 1 FROM driving_licence d WHERE d.check_id=%s
                   AND (d.expires_on=n.expires_on OR EXISTS (
                     SELECT 1 FROM licence_category k WHERE k.licence_id=d.id
                       AND k.expires_on=n.expires_on)))))""",
        (user_id, current_check_id),
    )
