"""Startup-only settings; all environment details are explicit configuration."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    """Validated API configuration, shared across requests without mutable session state."""

    app_env: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str = field(repr=False)
    push_key: bytes = field(repr=False)
    auth_key: bytes = field(repr=False)
    cors_origins: tuple[str, ...] = ()
    xroad_base_url: str = ""
    xroad_path: str = ""
    xroad_client: str = ""
    official_renewal_url: str = ""
    timeout_seconds: float = 3
    session_seconds: int = 1800
    session_warning_seconds: int = 120
    risk_days: int = 90
    stale_seconds: int = 86400
    pool_max: int = 8
    push_hosts: tuple[str, ...] = ()
    log_level: str = "INFO"
    login_max_attempts: int = 5
    login_source_max_attempts: int = 30
    login_window_seconds: int = 300

    medical_path: str = ""
    demo_login: bool = False
    vapid_key_file: str = ""
    vapid_subject: str = ""

    @classmethod
    def from_env(cls):
        """Load required settings and refuse using the supplied mock deployment in production."""
        env = os.environ
        mode = env.get("APP_ENV", "production")
        if mode not in {"development", "test"}:
            raise ValueError("The supplied mock X-Road deployment is development/test only")
        origins = tuple(x.strip() for x in env["CORS_ORIGINS"].split(",") if x.strip())
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path:
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
        if not origins:
            raise ValueError("CORS_ORIGINS must contain an explicit frontend origin")
        official_url = env["OFFICIAL_RENEWAL_URL"]
        if urlsplit(official_url).scheme != "https":
            raise ValueError("OFFICIAL_RENEWAL_URL must use HTTPS")
        base_url = env["XROAD_BASE_URL"].rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise ValueError("Invalid integration base URL")
        settings = cls(
            app_env=mode,
            medical_path=env.get("MOCK_MEDICAL_PATH", ""),
            demo_login=env.get("DEMO_CODE_LOGIN") == "1",
            vapid_key_file=env.get("VAPID_KEY_FILE", ""),
            vapid_subject=env.get("VAPID_SUBJECT", ""),
            db_host=env["DB_HOST"],
            db_port=int(env.get("DB_PORT", "5432")),
            db_name=env["DB_NAME"],
            db_user=env.get("DB_USER", "reminder_api"),
            db_password=Path(env["DB_PASSWORD_FILE"]).read_text().strip(),
            push_key=Path(env["PUSH_KEY_FILE"]).read_bytes().strip(),
            auth_key=bytes.fromhex(Path(env["AUTH_KEY_FILE"]).read_text().strip()),
            cors_origins=origins,
            xroad_base_url=base_url,
            xroad_path=env["XROAD_PATH"],
            xroad_client=env["XROAD_CLIENT"],
            official_renewal_url=official_url,
            timeout_seconds=float(env.get("XROAD_TIMEOUT_SECONDS", "3")),
            session_seconds=int(env.get("SESSION_SECONDS", "1800")),
            session_warning_seconds=int(env.get("SESSION_WARNING_SECONDS", "120")),
            risk_days=int(env.get("RISK_DAYS", "90")),
            stale_seconds=int(env.get("STALE_SECONDS", "86400")),
            pool_max=int(env.get("DB_POOL_MAX", "8")),
            push_hosts=tuple(x for x in env.get("PUSH_ALLOWED_HOSTS", "").split(",") if x),
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
            login_max_attempts=int(env.get("LOGIN_MAX_ATTEMPTS", "5")),
            login_source_max_attempts=int(env.get("LOGIN_SOURCE_MAX_ATTEMPTS", "30")),
            login_window_seconds=int(env.get("LOGIN_WINDOW_SECONDS", "300")),
        )
        if not 0 < settings.timeout_seconds <= 30 or not 1 <= settings.pool_max <= 32:
            raise ValueError("Invalid timeout or connection limit")
        if not 0 < settings.session_warning_seconds < settings.session_seconds <= 86400:
            raise ValueError("Invalid session lifetime or warning interval")
        if not 0 <= settings.risk_days <= 365 or settings.stale_seconds < 1:
            raise ValueError("Invalid expiry assessment settings")
        if len(settings.auth_key) != 32 or not 1 <= settings.login_max_attempts <= 100:
            raise ValueError("Invalid authentication key or attempt limit")
        if (
            not 1 <= settings.login_source_max_attempts <= 1000
            or not 1 <= settings.login_window_seconds <= 3600
        ):
            raise ValueError("Invalid source limit or throttle window")
        return settings
