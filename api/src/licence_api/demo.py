"""Prepare missing demo snapshots without modifying existing status history."""

from uuid import uuid4

from licence_api.config import Settings
from licence_api.store import (
    ISSUER,
    SYNTHETIC_PROFILES,
    Store,
    lock_user,
    medical_observation,
    utcnow,
)
from licence_api.upstream import XRoadClient


def main():
    settings = Settings.from_env()
    if not settings.demo_login:
        raise ValueError("Enable demo login before preparing demo snapshots")
    store = Store(settings)
    client = XRoadClient(settings)
    try:
        for name in ("valid", "expiring", "expired", "invalid", "unavailable", "slow", "medical"):
            subject = SYNTHETIC_PROFILES[name][0]
            with store.connection() as conn:
                user = conn.execute(
                    """SELECT id FROM user_account WHERE identity_issuer=%s
                       AND identity_subject=%s AND deleted_at IS NULL""",
                    (ISSUER, subject),
                ).fetchone()
                if not user:
                    raise ValueError("Run the explicit account seed first")
                uid = user["id"]
                lock_user(conn, uid)
                if settings.medical_path:
                    prepared = conn.execute(
                        """SELECT 1 FROM latest_successful_check c
                        JOIN medical_certificate m ON m.check_id=c.id WHERE c.user_id=%s
                        AND (EXISTS (SELECT 1 FROM driving_licence d WHERE d.check_id=c.id
                                     AND d.expiry_kind='driving_right')
                             OR NOT EXISTS (SELECT 1 FROM driving_licence d
                                            WHERE d.check_id=c.id))""",
                        (uid,),
                    ).fetchone()
                    if (
                        not prepared
                        and not conn.execute(
                            """SELECT 1 FROM status_check
                        WHERE user_id=%s AND outcome='failed' AND NOT EXISTS (
                        SELECT 1 FROM latest_successful_check WHERE user_id=%s) LIMIT 1""",
                            (uid, uid),
                        ).fetchone()
                    ):
                        store.refresh(conn, uid, subject, uuid4(), client, settings)
                    continue
                previous = conn.execute(
                    "SELECT driving_status FROM latest_successful_check WHERE user_id=%s", (uid,)
                ).fetchone()
                if name == "medical":
                    requirement, rows = medical_observation(conn, uid)
                    today = utcnow().date()
                    if requirement == "required" and any(
                        row["expires_on"] and 0 < (row["expires_on"] - today).days <= 90
                        for row in rows
                    ):
                        continue
                elif conn.execute(
                    "SELECT 1 FROM status_check WHERE user_id=%s LIMIT 1", (uid,)
                ).fetchone():
                    continue
                else:
                    store.refresh(conn, uid, subject, uuid4(), client, settings)
                if name == "medical":
                    # The registry has no certificate fields. Use a clearly synthetic
                    # standalone observation instead of attributing a certificate to it.
                    cid = uuid4()
                    conn.execute(
                        """INSERT INTO status_check(id,user_id,outcome,completed_at,trace_id,
                      xroad_request_id,driving_status,reason_code,medical_requirement,status_changed)
                      VALUES (%s,%s,'successful',clock_timestamp(),%s,'MOCK-NOT-XROAD-MEDICAL',
                      'at_risk','MEDICAL_EXPIRY_APPROACHING','required',%s)""",
                        (
                            cid,
                            uid,
                            uuid4(),
                            previous["driving_status"] != "at_risk" if previous else None,
                        ),
                    )
                    licence = uuid4()
                    conn.execute(
                        """INSERT INTO driving_licence(id,check_id,document_status,expires_on)
                       VALUES (%s,%s,'valid',CURRENT_DATE+730)""",
                        (licence, cid),
                    )
                    conn.execute(
                        "INSERT INTO licence_category(licence_id,category_code) VALUES (%s,'B')",
                        (licence,),
                    )
                    conn.execute(
                        """INSERT INTO medical_certificate(
                          id,check_id,certificate_status,expires_on)
                       VALUES (%s,%s,'valid',CURRENT_DATE+30)""",
                        (uuid4(), cid),
                    )
    finally:
        client.close()
        store.close()


if __name__ == "__main__":
    main()
