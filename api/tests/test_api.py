"""Real PostgreSQL/runtime-role and mock HTTP integration tests for frontend flows."""

import base64
import hashlib
import json
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from psycopg import errors

from conftest import TEST_PASSWORDS, login

pytestmark = pytest.mark.integration


def refresh(client, headers):
    response = client.post("/api/v1/me/driving-data/refresh", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def subscription_body():
    key = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    return {
        "endpoint": "https://push.example.test/synthetic",
        "keys": {
            "p256dh": base64.urlsafe_b64encode(key).decode().rstrip("="),
            "auth": base64.urlsafe_b64encode(b"mock-auth-secret").decode().rstrip("="),
        },
    }


def test_health_config_and_openapi(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/v1/config").json()["push"]["available"] is False
    assert client.get("/api/v1/auth/demo-users").status_code == 404
    assert client.get("/api/v1/config").json()["authenticationMode"] == "password"
    spec = client.get("/openapi.json").json()
    assert spec["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert "/api/v1/me/driving-data" in spec["paths"]
    assert client.get("/docs").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/me",
        "/me/driving-data",
        "/me/reminder-preferences",
        "/me/status-checks",
        "/me/notifications",
        "/me/renewal-guidance",
    ],
)
def test_protected_reads_require_login(client, path):
    response = client.get("/api/v1" + path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.headers["cache-control"] == "no-store"


def test_login_hashes_token_defaults_and_logout_revocation(client, owner):
    headers, session = login(client)
    stored = owner.execute("SELECT token_hash FROM web_session").fetchone()["token_hash"]
    assert bytes(stored) == hashlib.sha256(session["accessToken"].encode()).digest()
    assert client.get("/api/v1/me", headers=headers).json()["id"] == session["userId"]
    prefs = client.get("/api/v1/me/reminder-preferences", headers=headers).json()
    assert prefs["enabled"] is False and prefs["intervals"] == [90, 30, 7]
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    actions = owner.execute("SELECT action_code FROM audit_event").fetchall()
    assert {"authentication.succeeded", "session.revoked"} <= {
        row["action_code"] for row in actions
    }


def test_relogin_preserves_settings(client):
    headers, _ = login(client)
    client.put(
        "/api/v1/me/reminder-preferences", headers=headers, json={"enabled": True, "intervals": [7]}
    )
    headers, _ = login(client)
    assert client.get("/api/v1/me/reminder-preferences", headers=headers).json()["intervals"] == [7]


def test_invalid_login_and_expired_deleted_sessions(client, owner):
    invalid = client.post(
        "/api/v1/auth/login", json={"username": "does.not.exist", "password": "incorrect-password"}
    )
    assert invalid.status_code == 401
    headers, data = login(client)
    owner.execute("UPDATE web_session SET expires_at=created_at + interval '1 microsecond'")
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    headers, data = login(client)
    owner.execute(
        "UPDATE user_account SET deleted_at=clock_timestamp() WHERE id=%s", (data["userId"],)
    )
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "demo.valid", "password": TEST_PASSWORDS["valid"]},
        ).status_code
        == 401
    )


def test_empty_driving_data_and_successful_refresh(client, owner):
    headers, _ = login(client)
    assert client.get("/api/v1/me/driving-data", headers=headers).json()["status"] == "unknown"
    result = refresh(client, headers)
    assert result["check"]["outcome"] == "successful"
    assert result["check"]["statusChanged"] is None
    assert result["data"]["status"] == "valid"
    assert result["data"]["licences"][0]["expiryKind"] == "driving_right"
    assert result["data"]["licences"][0]["categories"][0]["expiresOn"]
    assert result["data"]["medicalCertificates"] == []
    assert result["data"]["medicalRequirement"] == "unknown"
    assert owner.execute("SELECT count(*) AS n FROM licence_category").fetchone()["n"] == 1
    second = refresh(client, headers)
    assert second["check"]["statusChanged"] is False
    assert client.get("/api/v1/me/status-checks?limit=1", headers=headers).json()["hasMore"] is True
    assert (
        client.get("/api/v1/me/status-checks/" + result["check"]["id"], headers=headers).json()[
            "isLatestSuccessful"
        ]
        is False
    )


@pytest.mark.parametrize(
    "persona,status", [("expiring", "at_risk"), ("expired", "invalid"), ("invalid", "invalid")]
)
def test_status_variations(client, persona, status):
    headers, _ = login(client, persona)
    result = refresh(client, headers)
    assert result["data"]["status"] == status
    assert result["data"]["explanations"]


def test_failed_refresh_preserves_success_and_recovers(client, owner):
    headers, data = login(client, "unavailable")
    # Prior synthetic success demonstrates fallback without changing the mock identity.
    check_id = uuid4()
    owner.execute(
        """INSERT INTO status_check(
        id,user_id,outcome,trace_id,completed_at,driving_status,medical_requirement)
        VALUES (%s,%s,'successful',%s,clock_timestamp(),'valid','unknown')""",
        (check_id, data["userId"], uuid4()),
    )
    result = refresh(client, headers)
    assert result["check"]["outcome"] == "failed"
    assert result["check"]["error"]["code"] == "XR_UNAVAILABLE"
    failed = owner.execute(
        "SELECT trace_id,xroad_request_id FROM status_check WHERE id=%s", (result["check"]["id"],)
    ).fetchone()
    assert failed["xroad_request_id"] == str(failed["trace_id"])
    assert result["data"]["status"] == "valid" and result["data"]["isStale"]
    checks = client.get("/api/v1/me/status-checks", headers=headers).json()["items"]
    assert next(row for row in checks if row["id"] == str(check_id))["isLatestSuccessful"]
    good_headers, _ = login(client, "valid")
    assert refresh(client, good_headers)["check"]["outcome"] == "successful"


def test_timeout_is_recorded_without_losing_access(client):
    headers, _ = login(client, "slow")
    result = refresh(client, headers)
    assert result["check"]["error"]["code"] == "XR_TIMEOUT"
    assert client.get("/api/v1/me", headers=headers).status_code == 200


def test_cross_user_check_access_is_not_found(client):
    alice, _ = login(client, "valid")
    bob, _ = login(client, "expiring")
    check_id = refresh(client, alice)["check"]["id"]
    assert client.get("/api/v1/me/status-checks/" + check_id, headers=bob).status_code == 404
    assert client.get("/api/v1/me/status-checks", headers=bob).json()["items"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"enabled": True, "intervals": [14]},
        {"enabled": True, "intervals": [7, 7]},
        {"enabled": "yes", "intervals": [7]},
        {"enabled": True, "intervals": [True]},
        {"enabled": True, "intervals": [7], "userId": "someone-else"},
    ],
)
def test_invalid_settings_do_not_change_saved_data(client, payload):
    headers, _ = login(client)
    assert (
        client.put("/api/v1/me/reminder-preferences", headers=headers, json=payload).status_code
        == 422
    )
    assert client.get("/api/v1/me/reminder-preferences", headers=headers).json()["enabled"] is False


def test_disabling_and_interval_changes_cancel_only_unsent_reminders(client, owner):
    headers, session = login(client, "expiring")
    result = refresh(client, headers)
    check_id = result["check"]["id"]
    licence = owner.execute(
        "SELECT * FROM driving_licence WHERE check_id=%s", (check_id,)
    ).fetchone()
    for days, state in ((90, "pending"), (30, "sent")):
        owner.execute(
            """INSERT INTO notification(id,user_id,check_id,document_kind,licence_id,expires_on,
            days_before,scheduled_at,channel,state,sent_at)
            VALUES (%s,%s,%s,'driving_licence',%s,%s,%s,
            clock_timestamp(),'in_app',%s,
            CASE WHEN %s='sent' THEN clock_timestamp() ELSE NULL END)""",
            (
                uuid4(),
                session["userId"],
                check_id,
                licence["id"],
                licence["expires_on"],
                days,
                state,
                state,
            ),
        )
    response = client.put(
        "/api/v1/me/reminder-preferences",
        headers=headers,
        json={"enabled": False, "intervals": [7]},
    )
    assert response.status_code == 200
    states = {row["state"] for row in owner.execute("SELECT state FROM notification").fetchall()}
    assert states == {"cancelled", "sent"}
    history = client.get("/api/v1/me/notifications?limit=1", headers=headers).json()
    assert len(history["items"]) == 1 and history["items"][0]["sentAt"]
    assert history["items"][0]["expiresOn"]


def test_old_medical_data_has_own_timestamp_and_is_not_relabelled_fresh(client, owner):
    headers, session = login(client)
    old = uuid4()
    owner.execute(
        """INSERT INTO status_check(
        id,user_id,requested_at,outcome,trace_id,completed_at,driving_status,medical_requirement)
        VALUES (%s,%s,clock_timestamp()-interval '2 days','successful',
        %s,clock_timestamp()-interval '2 days','valid','required')""",
        (old, session["userId"], uuid4()),
    )
    owner.execute(
        """INSERT INTO medical_certificate(id,check_id,certificate_status,expires_on)
        VALUES (%s,%s,'valid',CURRENT_DATE+7)""",
        (uuid4(), old),
    )
    result = refresh(client, headers)
    med = result["data"]["medicalCertificates"][0]
    assert med["isCurrent"] is False
    assert med["cachedAt"] != result["data"]["lastUpdatedAt"]
    assert result["data"]["nextExpiryIsStale"] is True
    guidance = client.get("/api/v1/me/renewal-guidance", headers=headers).json()
    assert any(item["code"] == "renew_medical" for item in guidance["actions"])
    assert guidance["externalNotice"] and guidance["fallbackMessage"]


def test_push_registration_is_encrypted_idempotent_owned_and_revocable(client, owner, settings):
    headers, _ = login(client)
    body = subscription_body()
    first = client.post("/api/v1/me/push-subscriptions", headers=headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post("/api/v1/me/push-subscriptions", headers=headers, json=body)
    assert first.json()["id"] == second.json()["id"]
    stored = owner.execute("SELECT encrypted_subscription FROM web_push_subscription").fetchone()
    ciphertext = bytes(stored["encrypted_subscription"])
    assert body["endpoint"].encode() not in ciphertext
    assert body["endpoint"].encode() in Fernet(settings.push_key).decrypt(ciphertext)
    other, _ = login(client, "expired")
    path = "/api/v1/me/push-subscriptions/" + first.json()["id"]
    assert client.delete(path, headers=other).status_code == 404
    assert client.delete(path, headers=headers).status_code == 204
    assert owner.execute("SELECT revoked_at FROM web_push_subscription").fetchone()["revoked_at"]


def test_push_endpoint_and_key_validation(client):
    headers, _ = login(client)
    body = subscription_body()
    body["endpoint"] = "http://127.0.0.1/private"
    assert (
        client.post("/api/v1/me/push-subscriptions", headers=headers, json=body).status_code == 422
    )
    body = subscription_body()
    body["keys"]["p256dh"] = "a" * 60
    assert (
        client.post("/api/v1/me/push-subscriptions", headers=headers, json=body).status_code == 422
    )


def test_cors_preflight_allows_only_configured_react_origins(client):
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    allowed = client.options("/api/v1/me/reminder-preferences", headers=headers)
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    headers["Origin"] = "https://untrusted.example.test"
    denied = client.options("/api/v1/me/reminder-preferences", headers=headers)
    assert "access-control-allow-origin" not in denied.headers


def test_safe_errors_limits_and_logs(client, caplog):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "demo.valid", "password": "secret-sensitive-input", "extra": "private"},
    )
    assert response.status_code == 422
    assert "secret-sensitive-input" not in response.text
    assert "secret-sensitive-input" not in caplog.text
    assert any(
        json.loads(record.message)["error"]["code"] == "VALIDATION_ERROR"
        for record in caplog.records
        if record.name == "licence_api"
    )
    assert response.json()["error"]["traceId"] == response.headers["x-request-id"]
    oversized = client.post("/api/v1/auth/login", content=b"x" * 65537)
    assert oversized.status_code == 413
    assert oversized.json()["error"]["traceId"] == oversized.headers["x-request-id"]
    headers, _ = login(client)
    assert client.get("/api/v1/me/notifications?limit=999", headers=headers).status_code == 422
    assert client.get("/api/v1/me/status-checks/not-a-uuid", headers=headers).status_code == 422


def test_runtime_cannot_mutate_audit_or_schema(client):
    with client.app.state.store.connection() as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("DELETE FROM audit_event")
    with client.app.state.store.connection() as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("CREATE TABLE forbidden_table(id integer)")


def test_reads_reassess_dates_after_snapshot(client, owner):
    headers, _ = login(client)
    result = refresh(client, headers)
    owner.execute(
        "UPDATE driving_licence SET expires_on=CURRENT_DATE-1 WHERE check_id=%s",
        (result["check"]["id"],),
    )
    data = client.get("/api/v1/me/driving-data", headers=headers).json()
    assert data["status"] == "invalid" and data["reasonCodes"] == ["LICENCE_EXPIRED"]


def test_pool_recovers_when_idle_database_connections_are_terminated(client, owner):
    headers, _ = login(client)
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    owner.execute("""SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                     WHERE datname=current_database() AND usename='reminder_api'""")
    assert client.get("/api/v1/me", headers=headers).status_code == 200
