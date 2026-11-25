"""Credential verification, no-bypass, rate-limit and seed lifecycle integration checks."""

import pytest

from conftest import TEST_PASSWORDS, login
from licence_api.authentication import PASSWORDS
from licence_api.seed import seed_accounts

pytestmark = pytest.mark.integration


def test_no_password_no_picker_and_no_implicit_account_creation(client, owner):
    before = owner.execute("SELECT count(*) AS n FROM user_account").fetchone()["n"]
    assert client.get("/api/v1/auth/demo-users").status_code == 404
    assert client.post("/api/v1/auth/login", json={"demoUser": "valid"}).status_code == 422
    assert client.post("/api/v1/auth/login", json={"username": "demo.valid"}).status_code == 422
    assert owner.execute("SELECT count(*) AS n FROM user_account").fetchone()["n"] == before
    assert owner.execute("SELECT count(*) AS n FROM web_session").fetchone()["n"] == 0


def test_wrong_unknown_disabled_and_deleted_accounts_have_same_generic_error(client, owner):
    wrong = client.post("/api/v1/auth/login", json={"username": "demo.valid", "password": "wrong"})
    unknown = client.post(
        "/api/v1/auth/login", json={"username": "does.not.exist", "password": "wrong"}
    )
    owner.execute("UPDATE password_credential SET is_enabled=false WHERE username='demo.valid'")
    disabled = client.post(
        "/api/v1/auth/login", json={"username": "demo.valid", "password": TEST_PASSWORDS["valid"]}
    )
    for response in (wrong, unknown, disabled):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID"
        assert response.headers["www-authenticate"] == "Bearer"
    assert (
        wrong.json()["error"]["message"]
        == unknown.json()["error"]["message"]
        == disabled.json()["error"]["message"]
    )


def test_account_throttle_is_shared_between_requests_and_expires(client, owner, settings):
    for _ in range(settings.login_max_attempts):
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "demo.valid", "password": "wrong"}
            ).status_code
            == 401
        )
    blocked = client.post(
        "/api/v1/auth/login", json={"username": "demo.valid", "password": TEST_PASSWORDS["valid"]}
    )
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    assert owner.execute("SELECT count(*) AS n FROM web_session").fetchone()["n"] == 0
    owner.execute("UPDATE login_throttle SET expires_at=clock_timestamp()-interval '1 second'")
    assert login(client)[1]["accessToken"]


def test_source_throttle_also_limits_unknown_users_and_ignores_forwarded_ip(client, settings):
    for i in range(settings.login_source_max_attempts):
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": f"unknown.user{i}", "password": "wrong"}
            ).status_code
            == 401
        )
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Forwarded-For": "192.0.2.123"},
        json={"username": "demo.valid", "password": TEST_PASSWORDS["valid"]},
    )
    assert response.status_code == 429


def test_disabling_credential_revokes_access_for_existing_token(client, owner):
    headers, _ = login(client)
    owner.execute("UPDATE password_credential SET is_enabled=false WHERE username='demo.valid'")
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_password_hashes_are_argon2_and_seed_is_idempotent(client, owner):
    before = owner.execute(
        "SELECT user_id,password_hash FROM password_credential ORDER BY user_id"
    ).fetchall()
    assert all(row["password_hash"].startswith("$argon2id$") for row in before)
    assert all(
        password not in row["password_hash"]
        for password in TEST_PASSWORDS.values()
        for row in before
    )
    headers, _ = login(client)
    seed_accounts(owner, TEST_PASSWORDS)
    after = owner.execute(
        "SELECT user_id,password_hash FROM password_credential ORDER BY user_id"
    ).fetchall()
    assert before == after
    assert client.get("/api/v1/me", headers=headers).status_code == 200


def test_explicit_password_rotation_invalidates_old_tokens_and_password(client, owner):
    headers, _ = login(client)
    replacements = {code: password + "-rotated" for code, password in TEST_PASSWORDS.items()}
    seed_accounts(owner, replacements, rotate=True)
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    old = client.post(
        "/api/v1/auth/login", json={"username": "demo.valid", "password": TEST_PASSWORDS["valid"]}
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login", json={"username": "demo.valid", "password": replacements["valid"]}
    )
    assert new.status_code == 200
    with pytest.raises(ValueError, match="differ"):
        seed_accounts(owner, TEST_PASSWORDS)


def test_unknown_user_and_real_hash_verification_are_both_called(client, monkeypatch):
    calls = []
    original = PASSWORDS.verify_and_update

    def observed(password, hashed):
        calls.append(hashed)
        return original(password, hashed)

    monkeypatch.setattr(PASSWORDS, "verify_and_update", observed)
    client.post("/api/v1/auth/login", json={"username": "does.not.exist", "password": "wrong"})
    login(client)
    assert len(calls) == 2 and all(item.startswith("$argon2id$") for item in calls)


def test_password_is_not_logged_or_returned_on_validation_error(client, caplog):
    password = TEST_PASSWORDS["valid"]
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "demo.valid", "password": password, "unexpected": "x"},
    )
    assert response.status_code == 422
    assert password not in response.text and password not in caplog.text


def test_seed_cli_writes_private_environment_and_reruns_without_resetting(
    client, owner, monkeypatch, tmp_path
):
    import json
    import os
    import sys

    from licence_api.seed import main

    target = tmp_path / "accounts.postman_environment.json"
    monkeypatch.setenv("DB_USER", os.environ["TEST_DATABASE_OWNER"])
    monkeypatch.setenv("DB_PASSWORD_FILE", os.environ["TEST_DATABASE_OWNER_PASSWORD_FILE"])
    monkeypatch.setattr(sys, "argv", ["seed", "--output", str(target), "--rotate-passwords"])
    main()
    private = json.loads(target.read_text())
    variables = {item["key"]: item["value"] for item in private["values"]}
    assert target.stat().st_mode & 0o077 == 0
    response = client.post(
        "/api/v1/auth/login",
        json={"username": variables["validUsername"], "password": variables["validPassword"]},
    )
    assert response.status_code == 200
    original = owner.execute(
        "SELECT user_id,password_hash FROM password_credential ORDER BY user_id"
    ).fetchall()
    monkeypatch.setattr(sys, "argv", ["seed", "--output", str(target)])
    main()
    assert (
        original
        == owner.execute(
            "SELECT user_id,password_hash FROM password_credential ORDER BY user_id"
        ).fetchall()
    )
    assert json.loads(target.read_text()) == private


def test_corrupt_hash_fails_closed_and_old_cost_hash_is_upgraded(client, owner):
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    owner.execute(
        "UPDATE password_credential SET password_hash=%s WHERE username='demo.valid'", ("x" * 40,)
    )
    failed = client.post(
        "/api/v1/auth/login", json={"username": "demo.valid", "password": TEST_PASSWORDS["valid"]}
    )
    assert failed.status_code == 401 and "x" * 40 not in failed.text
    previous = PasswordHash((Argon2Hasher(time_cost=2, memory_cost=19456, parallelism=1),)).hash(
        TEST_PASSWORDS["valid"]
    )
    owner.execute(
        "UPDATE password_credential SET password_hash=%s WHERE username='demo.valid'", (previous,)
    )
    login(client)
    current = owner.execute(
        "SELECT password_hash FROM password_credential WHERE username='demo.valid'"
    ).fetchone()["password_hash"]
    assert current != previous and PASSWORDS.verify(TEST_PASSWORDS["valid"], current)


@pytest.mark.parametrize(
    "key,value",
    [
        ("CORS_ORIGINS", "*"),
        ("CORS_ORIGINS", ""),
        ("OFFICIAL_RENEWAL_URL", "http://example.test"),
        ("XROAD_BASE_URL", "ftp://example.test"),
        ("XROAD_TIMEOUT_SECONDS", "31"),
        ("SESSION_WARNING_SECONDS", "99999"),
        ("RISK_DAYS", "999"),
        ("LOGIN_MAX_ATTEMPTS", "0"),
        ("LOGIN_SOURCE_MAX_ATTEMPTS", "0"),
    ],
)
def test_invalid_auth_and_security_settings_are_rejected(monkeypatch, key, value):
    from licence_api.config import Settings

    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        Settings.from_env()
