"""Public frontend request and response models, separate from the upstream schema."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    """Camel-case JSON contract with explicit rejection of unknown input fields."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class DemoLogin(Model):
    personal_code: str = Field(pattern=r"^[0-9]{11}$")


class LoginInput(Model):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class PreferencesInput(Model):
    enabled: bool = Field(strict=True)
    intervals: list[int] = Field(max_length=3)

    @field_validator("intervals", mode="before")
    @classmethod
    def intervals_are_supported(cls, values):
        """Reject coercion, unsupported lead times, and duplicate selections."""
        if not isinstance(values, list) or any(type(v) is not int for v in values):
            raise ValueError("Intervals must be integer days")
        if len(values) != len(set(values)) or set(values) - {90, 30, 7}:
            raise ValueError("Unsupported or duplicate interval")
        return sorted(values, reverse=True)


class SubscriptionKeys(Model):
    p256dh: str = Field(
        min_length=40,
        max_length=200,
        alias="p256dh",
        validation_alias=AliasChoices("p256dh", "p256Dh"),
    )
    auth: str = Field(min_length=16, max_length=100)


class SubscriptionInput(Model):
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: SubscriptionKeys


class Message(Model):
    code: str
    message: str


class ErrorBody(Message):
    trace_id: UUID
    fields: list[str] = []


class ErrorResponse(Model):
    error: ErrorBody


class SessionResponse(Model):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime
    session_warning_seconds: int
    user_id: UUID
    data_is_synthetic: bool


class Profile(Model):
    id: UUID
    display_name: str
    data_is_synthetic: bool
    session_expires_at: datetime
    session_warning_seconds: int


class Preferences(Model):
    enabled: bool
    intervals: list[int]
    available_intervals: list[int] = [90, 30, 7]
    updated_at: datetime
    delivery_available: bool = False


class Category(Model):
    code: str
    first_issued_on: date | None = None
    expires_on: date | None = None


class Licence(Model):
    id: UUID
    status: str
    issued_on: date | None
    expires_on: date | None
    expiry_kind: Literal["document", "driving_right"]
    categories: list[Category]
    cached_at: datetime
    is_current: bool


class MedicalCertificate(Model):
    id: UUID
    status: str
    issued_on: date | None
    expires_on: date | None
    cached_at: datetime
    is_current: bool


class Check(Model):
    id: UUID
    requested_at: datetime
    completed_at: datetime | None
    outcome: Literal["pending", "successful", "failed"]
    outcome_label: str
    driving_status: str | None
    status_changed: bool | None
    error: Message | None
    is_latest_successful: bool
    source: str
    source_label: str
    mocked: bool = True


class DrivingData(Model):
    renewal_actions: list[Literal["renew_licence", "renew_medical"]]
    status: Literal["valid", "at_risk", "invalid", "unknown"]
    status_label: str
    reason_codes: list[str]
    explanations: list[str]
    last_updated_at: datetime | None
    latest_check: Check | None
    is_stale: bool
    medical_requirement: str
    licences: list[Licence]
    medical_certificates: list[MedicalCertificate]
    next_expiry_date: date | None
    next_expiry_is_stale: bool
    warnings: list[Message]
    mocked: bool = True


class RefreshResponse(Model):
    check: Check
    data: DrivingData


class CheckList(Model):
    items: list[Check]
    limit: int
    has_more: bool


class Notification(Model):
    id: UUID
    sent_at: datetime
    document_kind: str
    document_label: str
    expires_on: date
    days_before: int
    message: str
    guidance_path: str = "/api/v1/me/renewal-guidance"


class NotificationList(Model):
    items: list[Notification]
    limit: int
    has_more: bool


class GuidanceAction(Model):
    code: str
    title: str
    description: str
    official_url: str


class Guidance(Model):
    actions: list[GuidanceAction]
    external_notice: str
    fallback_message: str
    official_url: str


class Subscription(Model):
    id: UUID
    created_at: datetime
    revoked_at: datetime | None
    delivery_available: bool = False


class Health(Model):
    status: Literal["ok"]


class PushConfig(Model):
    available: bool
    public_key: str | None


class FrontendConfig(Model):
    authentication_mode: Literal["password", "demo_code"]
    available_intervals: list[int]
    session_warning_seconds: int
    push: PushConfig
