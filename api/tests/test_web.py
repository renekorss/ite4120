"""Local demo session isolation, scheduling, delivery and retry integration tests."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from test_api import refresh, subscription_body

from conftest import login
from licence_api.delivery import tick
from licence_api.main import create_app


def test_demo_login(client, settings, owner):
    path = "/api/v1/auth/demo-login"
    assert client.post(path, json={"personalCode": "00000000001"}).status_code == 404
    with TestClient(create_app(replace(settings, demo_login=True))) as demo:
        token = demo.post(path, json={"personalCode": "00000000007"}).json()["accessToken"]
        headers = {"Authorization": f"Bearer {token}", "Accept-Language": "en"}
        assert demo.get("/api/v1/me", headers=headers).status_code == 200
        assert (
            demo.get("/api/v1/me/driving-data", headers=headers).json()["statusLabel"] == "Unknown"
        )
        assert demo.post(path, json={"personalCode": "00000000008"}).status_code == 401
        owner.execute("UPDATE password_credential SET is_enabled=false WHERE username='demo.valid'")
        assert demo.post(path, json={"personalCode": "00000000001"}).status_code == 401
        demo.post("/api/v1/auth/logout", headers=headers)
        assert demo.get("/api/v1/me", headers=headers).status_code == 401


@pytest.mark.parametrize(
    "outcome,code",
    [
        ("successful", None),
        ("failed", "PUSH_RETRY"),
        ("unknown", "PUSH_UNCONFIRMED"),
        ("failed", "PUSH_GONE"),
    ],
)
def test_due_delivery(client, settings, owner, outcome, code):
    headers, _ = login(client, "expiring")
    refresh(client, headers)
    client.put(
        "/api/v1/me/reminder-preferences",
        headers=headers,
        json={"enabled": True, "intervals": [30]},
    )
    assert (
        client.post(
            "/api/v1/me/push-subscriptions", headers=headers, json=subscription_body()
        ).status_code
        == 200
    )
    sent = []

    def send(config, session, subscription, row):
        sent.append(row["id"])
        assert set(subscription["keys"]) == {"auth", "p256dh"}
        assert subscription["endpoint"] == subscription_body()["endpoint"]
        return outcome, code

    for _ in range(2):
        tick(client.app.state.store, settings, None, 300, send)
    assert len(sent) == 1
    assert (
        owner.execute("SELECT outcome FROM notification_attempt").fetchone()["outcome"] == outcome
    )
    assert bool(client.get("/api/v1/me/notifications", headers=headers).json()["items"]) == (
        outcome == "successful"
    )
    client.put(
        "/api/v1/me/reminder-preferences",
        headers=headers,
        json={"enabled": False, "intervals": [30]},
    )
    tick(client.app.state.store, settings, None, 300, send)
    assert len(sent) == 1


def test_prepare_demo_and_reminder_worker_once(owner, monkeypatch, tmp_path):
    from sys import argv

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from licence_api import delivery, demo

    with pytest.raises(ValueError, match="demo login"):
        demo.main()
    monkeypatch.setenv("DEMO_CODE_LOGIN", "1")
    demo.main()
    demo.main()
    medical = owner.execute(
        "SELECT expires_on-CURRENT_DATE days FROM medical_certificate"
    ).fetchone()
    assert medical["days"] == 30
    assert owner.execute("SELECT count(*) n FROM medical_certificate").fetchone()["n"] == 1
    with TestClient(create_app()) as api:
        headers, _ = login(api, "medical")
        baseline = api.get("/api/v1/me/driving-data", headers=headers).json()
        for _ in range(2):
            result = refresh(api, headers)
            data = result["data"]
            assert result["check"]["drivingStatus"] == "at_risk"
            assert result["check"]["statusChanged"] is False
            assert data["status"] == "at_risk" and data["medicalRequirement"] == "required"
            assert (
                data["medicalCertificates"][0]["cachedAt"]
                == baseline["medicalCertificates"][0]["cachedAt"]
            )
            assert data["medicalCertificates"][0]["isCurrent"] is False
            assert data["nextExpiryDate"] == baseline["nextExpiryDate"]
        api.put(
            "/api/v1/me/reminder-preferences",
            headers=headers,
            json={"enabled": True, "intervals": [30]},
        )
        api.post("/api/v1/me/push-subscriptions", headers=headers, json=subscription_body())
        from licence_api.delivery import DUE

        assert (
            owner.execute("SELECT kind FROM (" + DUE + ") targets").fetchone()["kind"]
            == "medical_certificate"
        )
    demo.main()
    assert owner.execute("SELECT count(*) n FROM medical_certificate").fetchone()["n"] == 1
    owner.execute("UPDATE medical_certificate SET expires_on=CURRENT_DATE-1")
    with TestClient(create_app()) as api:
        headers, _ = login(api, "medical")
        data = api.get("/api/v1/me/driving-data", headers=headers).json()
        assert data["status"] == "invalid" and data["reasonCodes"] == ["MEDICAL_EXPIRED"]
    demo.main()
    assert owner.execute("SELECT count(*) n FROM medical_certificate").fetchone()["n"] == 2
    monkeypatch.setattr("sys.argv", [argv[0], "--once"])
    with pytest.raises(ValueError, match="VAPID_KEY_FILE"):
        delivery.main()
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "vapid.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    monkeypatch.setenv("VAPID_KEY_FILE", str(path))
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:demo@example.test")
    monkeypatch.setattr("sys.argv", [argv[0], "--once", "--retry-rejected"])
    delivery.main()
    monkeypatch.setenv("REMINDER_POLL_SECONDS", "0")
    with pytest.raises(ValueError, match="positive"):
        delivery.main()


@pytest.mark.parametrize(
    "status,expected",
    [
        (201, None),
        (410, "PUSH_GONE"),
        (503, "PUSH_RETRY"),
        (403, "PUSH_REJECTED"),
        (0, "PUSH_UNCONFIRMED"),
    ],
)
def test_encrypted_web_push(settings, tmp_path, monkeypatch, status, expected):
    import requests
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from licence_api.delivery import PushSession, public_key, transmit

    key = ec.generate_private_key(ec.SECP256R1())
    file = tmp_path / "key.pem"
    file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    config = replace(settings, vapid_key_file=str(file), vapid_subject="mailto:demo@example.test")
    assert len(public_key(config)) == 87

    def transport(self, request, **kwargs):
        assert request.headers["Authorization"].startswith("vapid ")
        assert request.headers["Content-Encoding"] == "aes128gcm"
        assert b"deadline" not in request.body
        assert kwargs["allow_redirects"] is False
        if not status:
            raise requests.Timeout()
        response = requests.Response()
        response.status_code = status
        response._content = b""
        return response

    monkeypatch.setattr(requests.Session, "send", transport)
    row = {"id": "test", "document_kind": "driving_licence", "expires_on": "2030-01-01"}
    with PushSession() as session:
        assert transmit(config, session, subscription_body(), row)[1] == expected
        legacy = subscription_body()
        legacy["keys"]["p256Dh"] = legacy["keys"].pop("p256dh")
        assert transmit(config, session, legacy, row)[1] == expected
        assert transmit(config, session, {"endpoint": "https://example.invalid"}, row)[1] == (
            "PUSH_ENDPOINT_REJECTED"
        )


def test_demo_rate_limit(settings, owner):
    with TestClient(
        create_app(replace(settings, demo_login=True, login_source_max_attempts=1))
    ) as demo:
        assert (
            demo.post("/api/v1/auth/demo-login", json={"personalCode": "00000000000"}).status_code
            == 401
        )
        r = demo.post("/api/v1/auth/demo-login", json={"personalCode": "00000000001"})
        assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_worker_rejects_missing_account_and_failed_tick(owner, monkeypatch, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from licence_api import delivery, demo

    monkeypatch.setenv("DEMO_CODE_LOGIN", "1")
    owner.execute(
        "UPDATE user_account SET deleted_at=clock_timestamp() WHERE identity_subject='demo-valid'"
    )
    with pytest.raises(ValueError, match="account seed"):
        demo.main()
    file = tmp_path / "vapid.pem"

    def make_key(curve):
        key = ec.generate_private_key(curve)
        file.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

    make_key(ec.SECP384R1())
    monkeypatch.setenv("VAPID_KEY_FILE", str(file))
    monkeypatch.setattr("sys.argv", ["worker", "--once"])
    with pytest.raises(ValueError, match="P-256"):
        delivery.main()
    make_key(ec.SECP256R1())
    with pytest.raises(ValueError, match="contact"):
        delivery.main()
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:demo@example.test")

    def failure(*args):
        raise RuntimeError("injected")

    monkeypatch.setattr(delivery, "tick", failure)
    with pytest.raises(SystemExit) as exc:
        delivery.main()
    assert exc.value.code == 1


def test_duplicate_workers_and_obsolete_deadline(client, settings, owner):
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from licence_api.delivery import deliver, schedule

    headers, session = login(client, "expiring")
    refresh(client, headers)
    client.put(
        "/api/v1/me/reminder-preferences",
        headers=headers,
        json={"enabled": True, "intervals": [30]},
    )
    client.post("/api/v1/me/push-subscriptions", headers=headers, json=subscription_body())
    with client.app.state.store.connection() as conn:
        schedule(conn)
    row = owner.execute("SELECT id,user_id FROM notification").fetchone()
    owner.execute(
        """INSERT INTO status_check(id,user_id,outcome,completed_at,trace_id,
          driving_status,medical_requirement,status_changed)
          VALUES (%s,%s,'successful',clock_timestamp(),%s,'valid','unknown',true)""",
        (uuid4(), session["userId"], uuid4()),
    )

    def run():
        deliver(
            client.app.state.store,
            settings,
            None,
            row,
            30,
            lambda *args: pytest.fail("obsolete reminder sent"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        for f in futures:
            f.result()
    assert owner.execute("SELECT state FROM notification").fetchone()["state"] == "cancelled"
    assert owner.execute("SELECT count(*) n FROM notification_attempt").fetchone()["n"] == 1


def test_combined_registry_refresh(settings, owner, monkeypatch):
    from licence_api import demo

    monkeypatch.setenv("DEMO_CODE_LOGIN", "1")
    monkeypatch.setenv("MOCK_MEDICAL_PATH", "/demo/v1/medical-certificate")
    demo.main()
    count = owner.execute("SELECT count(*) n FROM status_check").fetchone()["n"]
    demo.main()
    assert count == owner.execute("SELECT count(*) n FROM status_check").fetchone()["n"]
    with TestClient(
        create_app(replace(settings, medical_path="/demo/v1/medical-certificate"))
    ) as api:
        headers, _ = login(api, "medical")
        first = refresh(api, headers)["data"]
        again = refresh(api, headers)["data"]
        assert again["status"] == "at_risk"
        assert again["medicalRequirement"] == "required"
        for key in ("medicalCertificates", "licences"):
            assert again[key][0]["isCurrent"]
            assert again[key][0]["cachedAt"] == again["lastUpdatedAt"]
            assert again[key][0]["expiresOn"] == first[key][0]["expiresOn"]
        assert not any(w["code"] == "MEDICAL_DATA_UNAVAILABLE" for w in again["warnings"])
    with TestClient(create_app(replace(settings, medical_path="/missing"))) as api:
        headers, _ = login(api, "medical")
        failed = refresh(api, headers)
        assert failed["check"]["outcome"] == "failed"
        assert failed["data"]["lastUpdatedAt"] == again["lastUpdatedAt"]


@pytest.mark.parametrize(
    "profile,actions",
    [
        ("valid", []),
        ("expiring", ["renew_licence"]),
        ("medical", ["renew_medical"]),
        ("both", ["renew_licence", "renew_medical"]),
    ],
)
def test_card_actions_match_guidance(settings, owner, profile, actions):
    with TestClient(
        create_app(replace(settings, medical_path="/demo/v1/medical-certificate"))
    ) as api:
        headers, _ = login(api, profile)
        assert refresh(api, headers)["data"]["renewalActions"] == actions
        guidance = api.get("/api/v1/me/renewal-guidance", headers=headers).json()
        assert [action["code"] for action in guidance["actions"]] == (actions or ["check_status"])


@pytest.mark.parametrize("days", [90, 30, 7])
def test_category_deadline_reminder(client, settings, owner, days):
    headers, _ = login(client, "valid")
    refresh(client, headers)
    expiry = (
        owner.execute(
            "UPDATE licence_category SET expires_on=CURRENT_DATE+%s RETURNING expires_on", (days,)
        )
        .fetchone()["expires_on"]
        .isoformat()
    )
    data = client.get("/api/v1/me/driving-data", headers=headers).json()
    assert data["nextExpiryDate"] == expiry
    client.put(
        "/api/v1/me/reminder-preferences",
        headers=headers,
        json={"enabled": True, "intervals": [days]},
    )
    client.post("/api/v1/me/push-subscriptions", headers=headers, json=subscription_body())
    for _ in range(2):
        tick(client.app.state.store, settings, None, 300, lambda *args: ("successful", None))
    notices = client.get("/api/v1/me/notifications", headers=headers).json()["items"]
    assert len(notices) == 1
    assert notices[0]["expiresOn"] == expiry and notices[0]["daysBefore"] == days


def test_recent_notification_history(client, owner):
    headers, user = login(client)
    check = refresh(client, headers)["check"]["id"]
    owner.execute(
        """WITH licences AS (
           INSERT INTO driving_licence(id,check_id,document_status,expires_on)
           SELECT gen_random_uuid(),%s,'valid',CURRENT_DATE+n FROM generate_series(1,21) n
           RETURNING id,check_id,expires_on)
           INSERT INTO notification(id,user_id,check_id,document_kind,licence_id,expires_on,
             days_before,scheduled_at,channel,state,created_at,sent_at)
           SELECT gen_random_uuid(),%s,check_id,'driving_licence',id,expires_on,7,
             CURRENT_DATE-30,'in_app','sent',CURRENT_DATE-30,
             CURRENT_DATE-(expires_on-CURRENT_DATE) FROM licences""",
        (check, user["userId"]),
    )
    result = client.get("/api/v1/me/notifications", headers=headers).json()
    assert result["hasMore"] and len(result["items"]) == 20
    dates = [n["sentAt"] for n in result["items"]]
    assert dates == sorted(dates, reverse=True)
    assert all(n["documentLabel"] and n["expiresOn"] for n in result["items"])
