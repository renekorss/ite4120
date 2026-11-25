"""Explicit operator-only synthetic account provisioning through normal password credentials."""

import argparse
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from licence_api.authentication import PASSWORDS
from licence_api.config import Settings
from licence_api.store import ISSUER, SYNTHETIC_PROFILES


def seed_accounts(conn, passwords, rotate=False):
    """Create seed identities/credentials once; refuse implicit password resets."""
    for code, (subject, _source_code, label) in SYNTHETIC_PROFILES.items():
        row = conn.execute(
            """INSERT INTO user_account(id,identity_issuer,identity_subject) VALUES (%s,%s,%s)
               ON CONFLICT(identity_issuer,identity_subject) DO UPDATE
               SET identity_subject=EXCLUDED.identity_subject RETURNING id,deleted_at""",
            (uuid4(), ISSUER, subject),
        ).fetchone()
        if row["deleted_at"]:
            raise ValueError("Seed account is deactivated; restore it explicitly before seeding")
        user_id = row["id"]
        existing = conn.execute(
            "SELECT * FROM password_credential WHERE user_id=%s", (user_id,)
        ).fetchone()
        password = passwords[code]
        if existing and not rotate:
            if existing["username"] != f"demo.{code}" or not PASSWORDS.verify(
                password, existing["password_hash"]
            ):
                raise ValueError(
                    "Seed credentials differ; use explicit password rotation to replace them"
                )
        else:
            conn.execute(
                """INSERT INTO password_credential(user_id,username,password_hash,display_name)
                   VALUES (%s,%s,%s,%s) ON CONFLICT(user_id) DO UPDATE
                   SET password_hash=EXCLUDED.password_hash,updated_at=clock_timestamp()""",
                (user_id, f"demo.{code}", PASSWORDS.hash(password), label),
            )
            conn.execute(
                """UPDATE web_session SET revoked_at=clock_timestamp()
                   WHERE user_id=%s AND revoked_at IS NULL""",
                (user_id,),
            )
            conn.execute(
                """INSERT INTO audit_event(
                   id,subject_user_id,actor_kind,action_code,outcome,trace_id)
                   VALUES (%s,%s,'system',%s,'success',%s)""",
                (
                    uuid4(),
                    user_id,
                    "credentials.rotated" if existing else "credentials.seeded",
                    uuid4(),
                ),
            )
        created = conn.execute(
            """INSERT INTO reminder_preference(user_id) VALUES (%s)
           ON CONFLICT DO NOTHING RETURNING user_id""",
            (user_id,),
        ).fetchone()
        if created:
            for days in (90, 30, 7):
                conn.execute(
                    "INSERT INTO reminder_interval(user_id,days_before) VALUES (%s,%s)",
                    (user_id, days),
                )


def main():
    """Seed only on explicit invocation; write passwords to an ignored owner-only environment."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--rotate-passwords", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    if settings.app_env not in {"development", "test"}:
        raise ValueError("Synthetic account seeding is not allowed in production")
    target = Path(args.output)
    existing = json.loads(target.read_text()) if target.exists() else {"values": []}
    saved = {item["key"]: item["value"] for item in existing["values"]}
    passwords = {
        code: (
            secrets.token_urlsafe(32)
            if args.rotate_passwords
            else saved.get(f"{code}Password") or secrets.token_urlsafe(32)
        )
        for code in SYNTHETIC_PROFILES
    }
    with psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        row_factory=dict_row,
    ) as conn:
        seed_accounts(conn, passwords, rotate=args.rotate_passwords)
    values = [{"key": "apiBaseUrl", "value": "http://127.0.0.1:18080", "enabled": True}]
    for code in SYNTHETIC_PROFILES:
        values += [
            {"key": f"{code}Username", "value": f"demo.{code}", "enabled": True},
            {"key": f"{code}Password", "value": passwords[code], "type": "secret", "enabled": True},
        ]
    environment = {
        "name": "Driving Licence Reminder — local seeded accounts",
        "_postman_variable_scope": "environment",
        "values": values,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as output:
        json.dump(environment, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(
        "Seeded credential-backed synthetic accounts. "
        "Passwords are only in the private Postman environment file."
    )


if __name__ == "__main__":
    main()
