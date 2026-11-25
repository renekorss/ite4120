"""Normal password verification and shared login throttling; no account-selection bypass."""

import hashlib
import hmac
import math
import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError

from licence_api import models as m
from licence_api.store import ISSUER, audit, utcnow

PASSWORDS = PasswordHash.recommended()


class PasswordAuthentication:
    """Use maintained Argon2id hashing and comparable work for unknown usernames."""

    def __init__(self, settings):
        self.settings = settings
        self.dummy_hash = PASSWORDS.hash(secrets.token_urlsafe(32))

    def _bucket(self, scope, value):
        return hmac.digest(self.settings.auth_key, f"{scope}:{value}".encode(), "sha256")

    def _attempt(self, conn, key, maximum):
        now = utcnow()
        row = conn.execute(
            """INSERT INTO login_throttle(bucket_hash,attempts,expires_at) VALUES (%s,1,%s)
               ON CONFLICT(bucket_hash) DO UPDATE SET
               attempts=CASE WHEN login_throttle.expires_at<=%s THEN 1
                   ELSE LEAST(login_throttle.attempts+1,32767) END,
               expires_at=CASE WHEN login_throttle.expires_at<=%s THEN EXCLUDED.expires_at
                   ELSE login_throttle.expires_at END RETURNING attempts,expires_at""",
            (key, now + timedelta(seconds=self.settings.login_window_seconds), now, now),
        ).fetchone()
        if row["attempts"] > maximum:
            return max(1, math.ceil((row["expires_at"] - now).total_seconds()))
        return None

    def demo_login(self, conn, personal_code, source, trace_id):
        """Allow only explicitly seeded synthetic identities in demo deployments."""
        profiles = ("valid", "expiring", "expired", "invalid", "unavailable", "slow", "medical")
        names = {f"{i:011}": f"demo.{name}" for i, name in enumerate(profiles, 1)}
        conn.execute("DELETE FROM login_throttle WHERE expires_at<=%s", (utcnow(),))
        wait = self._attempt(
            conn, self._bucket("demo-source", source), self.settings.login_source_max_attempts
        )
        if wait:
            audit(
                conn,
                "authentication.throttled",
                trace_id,
                outcome="failure",
                error_code="AUTH_RATE_LIMITED",
            )
            conn.commit()
            raise HTTPException(429, "AUTH_RATE_LIMITED", headers={"Retry-After": str(wait)})
        row = conn.execute(
            """SELECT c.user_id,u.identity_issuer FROM password_credential c
               JOIN user_account u ON u.id=c.user_id WHERE c.username=%s AND c.is_enabled
               AND u.identity_issuer=%s AND u.deleted_at IS NULL FOR UPDATE OF u,c""",
            (names.get(personal_code), ISSUER),
        ).fetchone()
        if not row:
            audit(
                conn,
                "authentication.failed",
                trace_id,
                outcome="failure",
                error_code="AUTH_INVALID",
            )
            conn.commit()
            raise HTTPException(401, "AUTH_INVALID")
        return self.issue(conn, row, trace_id)

    def login(self, conn, payload, source_address, trace_id):
        """Verify credentials before issuing a session; commit failed-attempt evidence."""
        conn.execute("DELETE FROM login_throttle WHERE expires_at<=%s", (utcnow(),))
        source_key = self._bucket("source", source_address)
        account_key = self._bucket("account", payload.username)
        # Source first: blocked sources cannot create unlimited unknown-account buckets.
        wait = self._attempt(conn, source_key, self.settings.login_source_max_attempts)
        if wait is None:
            wait = self._attempt(conn, account_key, self.settings.login_max_attempts)
        if wait:
            audit(
                conn,
                "authentication.throttled",
                trace_id,
                outcome="failure",
                error_code="AUTH_RATE_LIMITED",
            )
            conn.commit()
            raise HTTPException(429, "AUTH_RATE_LIMITED", headers={"Retry-After": str(wait)})
        row = conn.execute(
            """SELECT c.*,u.identity_issuer,u.deleted_at FROM password_credential c
               JOIN user_account u ON u.id=c.user_id WHERE c.username=%s FOR UPDATE OF c,u""",
            (payload.username,),
        ).fetchone()
        try:
            verified, updated_hash = PASSWORDS.verify_and_update(
                payload.password.get_secret_value(),
                row["password_hash"] if row else self.dummy_hash,
            )
        except (PwdlibError, ValueError):
            verified, updated_hash = False, None
        if not row or not verified or not row["is_enabled"] or row["deleted_at"]:
            audit(
                conn,
                "authentication.failed",
                trace_id,
                row["user_id"] if row else None,
                "failure",
                "AUTH_INVALID",
            )
            conn.commit()
            raise HTTPException(401, "AUTH_INVALID")
        if updated_hash:
            conn.execute(
                """UPDATE password_credential SET password_hash=%s,updated_at=clock_timestamp()
                   WHERE user_id=%s""",
                (updated_hash, row["user_id"]),
            )
        conn.execute("DELETE FROM login_throttle WHERE bucket_hash=%s", (account_key,))
        return self.issue(conn, row, trace_id)

    def issue(self, conn, row, trace_id):
        """Issue an opaque, revocable session for a verified account."""
        token = secrets.token_urlsafe(32)
        expires = utcnow() + timedelta(seconds=self.settings.session_seconds)
        conn.execute(
            "INSERT INTO web_session(id,user_id,token_hash,expires_at) VALUES (%s,%s,%s,%s)",
            (uuid4(), row["user_id"], hashlib.sha256(token.encode()).digest(), expires),
        )
        audit(conn, "authentication.succeeded", trace_id, row["user_id"])
        return m.SessionResponse(
            access_token=token,
            expires_at=expires,
            session_warning_seconds=self.settings.session_warning_seconds,
            user_id=row["user_id"],
            data_is_synthetic=row["identity_issuer"] == ISSUER,
        )
