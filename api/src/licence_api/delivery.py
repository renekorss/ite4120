"""Schedule and deliver one Web Push reminder per document deadline and interval."""

import argparse
import base64
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush

from licence_api.config import Settings
from licence_api.store import LATEST_MEDICAL, Store, lock_user, utcnow

LOG = logging.getLogger("delivery")


def public_key(settings):
    """Derive the browser application server key from the operator's VAPID key."""
    if not settings.vapid_key_file:
        return None
    key = serialization.load_pem_private_key(Path(settings.vapid_key_file).read_bytes(), None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("Expected a P-256 VAPID key")
    if not settings.vapid_subject.startswith(("mailto:", "https://")):
        raise ValueError("A VAPID contact is required")
    raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class PushSession(requests.Session):
    """Send to the validated provider only, including on redirect responses."""

    def post(self, url, **kwargs):
        return super().post(url, allow_redirects=False, **kwargs)


# Restrict scheduling to the latest verified document snapshot. On restart, due
# items are recovered throughout their UTC day. Older intervals are not backfilled.
DUE = f"""
WITH documents AS (
  SELECT c.user_id,c.id check_id,d.id licence_id,NULL::uuid medical_id,
         'driving_licence' kind,t.expires_on,t.category_code
  FROM latest_successful_check c JOIN driving_licence d ON d.check_id=c.id
  CROSS JOIN LATERAL (
    SELECT d.expires_on,NULL::varchar category_code
    UNION ALL
    SELECT k.expires_on,min(k.category_code) FROM licence_category k
    WHERE k.licence_id=d.id AND k.expires_on IS DISTINCT FROM d.expires_on GROUP BY k.expires_on
  ) t
  UNION ALL
  SELECT c.user_id,c.id,NULL,m.id,'medical_certificate',m.expires_on,NULL
  FROM ({LATEST_MEDICAL}) c JOIN medical_certificate m ON m.check_id=c.id
  WHERE c.medical_requirement='required'
)
SELECT d.*,i.days_before,s.id subscription_id FROM documents d
JOIN user_account u ON u.id=d.user_id AND u.deleted_at IS NULL
JOIN reminder_preference p ON p.user_id=d.user_id AND p.enabled
JOIN reminder_interval i ON i.user_id=d.user_id AND d.expires_on-i.days_before=CURRENT_DATE
JOIN LATERAL (SELECT id FROM web_push_subscription WHERE user_id=d.user_id
              AND revoked_at IS NULL ORDER BY created_at DESC,id DESC LIMIT 1) s ON true
"""


def schedule(conn):
    """Create durable due rows; repeated ticks preserve accepted/uncertain deliveries."""
    conn.execute(
        """INSERT INTO notification(id,user_id,check_id,document_kind,licence_id,
           medical_certificate_id,category_code,expires_on,days_before,scheduled_at,channel,subscription_id)
           SELECT gen_random_uuid(),user_id,check_id,kind,licence_id,medical_id,category_code,
           expires_on,
           days_before,CURRENT_TIMESTAMP,'web_push',subscription_id FROM ("""
        + DUE
        + """) targets ON CONFLICT (user_id,document_kind,expires_on,days_before) DO UPDATE
          SET state='pending',subscription_id=EXCLUDED.subscription_id,channel='web_push',
              check_id=EXCLUDED.check_id,licence_id=EXCLUDED.licence_id,
              medical_certificate_id=EXCLUDED.medical_certificate_id,category_code=EXCLUDED.category_code,error_code=NULL
          WHERE notification.state='cancelled' AND NOT EXISTS (
          SELECT 1 FROM notification_attempt a WHERE a.notification_id=notification.id
          AND a.outcome IN ('unknown','pending','successful'))"""
    )


def transmit(settings, session, subscription, row):
    """Return a safe classification; ambiguous transmissions are never repeated automatically."""
    parsed = urlsplit(subscription["endpoint"])
    if (
        parsed.scheme != "https"
        or parsed.hostname not in settings.push_hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        return "failed", "PUSH_ENDPOINT_REJECTED"
    # Earlier API versions serialized the browser-standard key as p256Dh.
    # Read both representations so registered browsers survive the upgrade.
    keys = subscription.get("keys", {})
    if "p256dh" not in keys and "p256Dh" in keys:
        subscription = {**subscription, "keys": {**keys, "p256dh": keys["p256Dh"]}}
    label = (
        "Driving licence" if row["document_kind"] == "driving_licence" else "Medical certificate"
    )
    body = f"{label} deadline: {row['expires_on']}. Open renewal instructions."
    try:
        webpush(
            subscription,
            json.dumps({"title": "Driving Licence Reminder", "body": body, "tag": str(row["id"])}),
            vapid_private_key=settings.vapid_key_file,
            vapid_claims={"sub": settings.vapid_subject},
            requests_session=session,
            ttl=86400,
            timeout=5,
        )
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status in (404, 410):
            return "failed", "PUSH_GONE"
        if status == 429 or 500 <= status < 600:
            return "failed", "PUSH_RETRY"
        return "failed", "PUSH_REJECTED"
    except requests.RequestException:
        return "unknown", "PUSH_UNCONFIRMED"
    return "successful", None


def deliver(store, settings, session, item, retry_seconds, send):
    """Persist an attempt before external I/O and serialize final eligibility against changes."""
    attempt = uuid4()
    with store.connection() as conn:
        if not lock_user(conn, item["user_id"]):
            return
        row = conn.execute(
            """UPDATE notification SET state='processing',
            claimed_until=clock_timestamp()+interval '2 minutes' WHERE id=%s AND
            (state='pending' OR (state='failed' AND error_code='PUSH_RETRY'
            AND scheduled_at<=clock_timestamp())) RETURNING *""",
            (item["id"],),
        ).fetchone()
        if not row:
            return
        conn.execute(
            """INSERT INTO notification_attempt(id,notification_id,attempt_number,trace_id,outcome)
          SELECT %s,%s,COALESCE(MAX(attempt_number),0)+1,%s,'pending' FROM notification_attempt
          WHERE notification_id=%s""",
            (attempt, row["id"], attempt, row["id"]),
        )
    with store.connection() as conn:
        lock_user(conn, row["user_id"])
        target = conn.execute(
            "SELECT * FROM ("
            + DUE
            + """) t WHERE user_id=%s AND kind=%s
          AND expires_on=%s AND days_before=%s AND subscription_id=%s""",
            (
                row["user_id"],
                row["document_kind"],
                row["expires_on"],
                row["days_before"],
                row["subscription_id"],
            ),
        ).fetchone()
        sub = conn.execute(
            """SELECT encrypted_subscription FROM web_push_subscription
          WHERE id=%s AND revoked_at IS NULL FOR UPDATE""",
            (row["subscription_id"],),
        ).fetchone()
        active = conn.execute(
            "SELECT state FROM notification WHERE id=%s FOR UPDATE", (row["id"],)
        ).fetchone()
        if target and sub and active["state"] == "processing":
            data = json.loads(
                Fernet(settings.push_key).decrypt(bytes(sub["encrypted_subscription"]))
            )
            outcome, code = send(settings, session, data, row)
        else:
            outcome, code = "failed", "PUSH_CANCELLED"
        state = (
            "sent"
            if outcome == "successful"
            else ("cancelled" if code == "PUSH_CANCELLED" else "failed")
        )
        if code == "PUSH_GONE":
            conn.execute(
                "UPDATE web_push_subscription SET revoked_at=clock_timestamp() WHERE id=%s",
                (row["subscription_id"],),
            )
        conn.execute(
            """UPDATE notification_attempt SET outcome=%s,error_code=%s,
             completed_at=clock_timestamp() WHERE id=%s""",
            (outcome, code, attempt),
        )
        conn.execute(
            """UPDATE notification SET state=%s,error_code=%s,claimed_until=NULL,
          sent_at=CASE WHEN %s THEN clock_timestamp() END,scheduled_at=CASE WHEN %s
          THEN clock_timestamp()+make_interval(secs=>%s) ELSE scheduled_at END WHERE id=%s""",
            (state, code, state == "sent", code == "PUSH_RETRY", retry_seconds, row["id"]),
        )
        conn.execute(
            """INSERT INTO audit_event(id,subject_user_id,actor_kind,action_code,
          outcome,error_code,trace_id) VALUES (%s,%s,'system','push.delivery',%s,%s,%s)""",
            (
                uuid4(),
                row["user_id"],
                {"successful": "success", "failed": "failure", "unknown": "unknown"}[outcome],
                code,
                attempt,
            ),
        )


def tick(store, settings, session, retry_seconds, send=transmit):
    """Reconcile uncertain attempts, enqueue due reminders and send a bounded batch."""
    with store.connection() as conn:
        conn.execute("""WITH expired AS (UPDATE notification SET state='failed',
          error_code='PUSH_UNCONFIRMED',claimed_until=NULL WHERE state='processing'
          AND claimed_until<clock_timestamp() RETURNING id)
          UPDATE notification_attempt SET outcome='unknown',error_code='PUSH_UNCONFIRMED',
          completed_at=clock_timestamp() WHERE outcome='pending'
          AND notification_id IN (SELECT id FROM expired)""")
        schedule(conn)
        items = conn.execute("""SELECT id,user_id FROM notification WHERE channel='web_push'
          AND scheduled_at<=clock_timestamp() AND (state='pending' OR
          (state='failed' AND error_code='PUSH_RETRY'))
          ORDER BY scheduled_at,id LIMIT 100""").fetchall()
    for item in items:
        deliver(store, settings, session, item, retry_seconds, send)


def main():
    """Run continuously, or execute one operator-triggered scheduling pass."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--retry-rejected",
        action="store_true",
        help="Reconsider explicitly rejected due deliveries after fixing their cause",
    )
    args = parser.parse_args()
    settings = Settings.from_env()
    if not public_key(settings):
        raise ValueError("VAPID_KEY_FILE is required")
    interval = int(os.environ.get("REMINDER_POLL_SECONDS", "30"))
    retry = int(os.environ.get("REMINDER_RETRY_SECONDS", "300"))
    if min(interval, retry) < 1:
        raise ValueError("Worker intervals must be positive")
    store = Store(settings)
    try:
        if args.retry_rejected:
            with store.connection() as conn:
                conn.execute("""UPDATE notification SET state='pending',error_code=NULL,
                    scheduled_at=clock_timestamp() WHERE channel='web_push' AND state='failed'
                    AND error_code='PUSH_REJECTED' AND expires_on-days_before=CURRENT_DATE""")
        with PushSession() as session:
            while True:
                try:
                    tick(store, settings, session, retry)
                except Exception:
                    LOG.error(
                        json.dumps(
                            {
                                "@timestamp": utcnow().isoformat(),
                                "event.action": "worker.tick",
                                "event.outcome": "failure",
                                "error.code": "WORKER_FAILURE",
                                "trace.id": str(uuid4()),
                            }
                        )
                    )
                    if args.once:
                        raise SystemExit(1) from None
                if args.once:
                    break
                time.sleep(interval)
    finally:
        store.close()


if __name__ == "__main__":
    main()
