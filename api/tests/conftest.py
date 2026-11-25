"""Fixtures restricted to the disposable API test database."""

import os
import secrets
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from licence_api.config import Settings
from licence_api.main import create_app
from licence_api.seed import seed_accounts
from licence_api.store import SYNTHETIC_PROFILES

TEST_PASSWORDS = {code: secrets.token_urlsafe(24) for code in SYNTHETIC_PROFILES}


@pytest.fixture
def settings():
    return Settings.from_env()


@pytest.fixture
def owner(settings):
    assert settings.app_env == "test", "Use scripts/test-api.sh with disposable storage"
    password = Path(os.environ["TEST_DATABASE_OWNER_PASSWORD_FILE"]).read_text().strip()
    with psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=os.environ["TEST_DATABASE_OWNER"],
        password=password,
        row_factory=dict_row,
        autocommit=True,
    ) as conn:
        conn.execute("TRUNCATE user_account,login_throttle CASCADE")
        seed_accounts(conn, TEST_PASSWORDS)
        yield conn


@pytest.fixture
def client(settings, owner):
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def login(client, user="valid"):
    response = client.post(
        "/api/v1/auth/login", json={"username": f"demo.{user}", "password": TEST_PASSWORDS[user]}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return {"Authorization": "Bearer " + data["accessToken"]}, data
