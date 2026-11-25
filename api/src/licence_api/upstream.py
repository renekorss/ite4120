"""Validate the selected external contract without leaking its data into frontend JSON."""

import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

CATEGORIES = {
    "AM",
    "A1",
    "A2",
    "A",
    "B1",
    "B",
    "BE",
    "C1",
    "C1E",
    "C",
    "CE",
    "D1",
    "D1E",
    "D",
    "DE",
    "T",
}
INVALID_REASONS = {
    "JUHILUBA_EI_OLE_KEHTIV",
    "KEHTIVAT_JUHILUBA_EI_LEITUD",
    "JUHTIMISOIGUS_EI_OLE_KEHTIV",
}


class UpstreamError(Exception):
    """Safe integration failure code, independent of upstream technical details."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class SourceCategory(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    kood: str
    esmakordseValjastamiseKp: str
    kehtivusKp: str


class SourceResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    staatus: Literal["kehtiv", "kehtetu"]
    loaTyyp: Literal["JUHILUBA", "ESMANE"] | None = None
    valjastamisKp: str | None = None
    juhtimisOiguseLoppKp: str | None = None
    kategooriad: list[SourceCategory] | None = None
    pohjuseKood: str | None = None


@dataclass(frozen=True)
class Observation:
    """Minimized source observation; no name, personal code or document number."""

    status: str
    reason: str | None
    issued_on: date | None
    expires_on: date | None
    categories: tuple[tuple[str, date, date], ...]
    request_id: str


def parse_source(payload, request_id):
    """Reject incomplete/inconsistent source data rather than interpreting it as valid."""
    try:
        source = SourceResponse.model_validate(payload)
        if source.staatus == "kehtetu":
            if source.pohjuseKood not in INVALID_REASONS:
                raise ValueError("Unknown invalid reason")
            return Observation("invalid", source.pohjuseKood, None, None, (), request_id)
        if not source.loaTyyp or not source.kategooriad or len(source.kategooriad) > 20:
            raise ValueError("Missing licence fields")
        issued = datetime.strptime(source.valjastamisKp or "", "%d.%m.%Y").date()
        expires = datetime.strptime(source.juhtimisOiguseLoppKp or "", "%d.%m.%Y").date()
        categories = []
        for category in source.kategooriad:
            first = datetime.strptime(category.esmakordseValjastamiseKp, "%d.%m.%Y").date()
            end = datetime.strptime(category.kehtivusKp, "%d.%m.%Y").date()
            if category.kood not in CATEGORIES or end < first:
                raise ValueError("Invalid category")
            categories.append((category.kood, first, end))
        if expires < issued or len({c[0] for c in categories}) != len(categories):
            raise ValueError("Inconsistent dates or categories")
        return Observation("valid", None, issued, expires, tuple(categories), request_id)
    except (ValidationError, ValueError, TypeError) as exc:
        raise UpstreamError("XR_INVALID_RESPONSE") from exc


class XRoadClient:
    """Connection-reusing, bounded mock integration client; automatic retries disabled."""

    def __init__(self, settings):
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.xroad_base_url,
            timeout=httpx.Timeout(settings.timeout_seconds, connect=2, pool=1),
            limits=httpx.Limits(max_connections=settings.pool_max, max_keepalive_connections=4),
            follow_redirects=False,
            trust_env=False,
        )

    def close(self):
        self.client.close()

    def fetch(self, personal_code, trace_id):
        """Fetch only a configured synthetic identity, with safe generated correlation IDs."""
        payload = self._post(self.settings.xroad_path, {"isikukood": personal_code}, trace_id)
        return parse_source(payload, str(trace_id))

    def fetch_medical(self, scenario, trace_id):
        """Read the independent synthetic medical registry using the same bounded transport."""
        payload = self._post(self.settings.medical_path, {"scenario": scenario}, trace_id)
        try:
            if payload["required"] is not True:
                raise ValueError("Unsupported demo certificate")
            return date.fromisoformat(payload["expiresOn"])
        except (KeyError, ValueError, TypeError) as exc:
            raise UpstreamError("XR_INVALID_RESPONSE") from exc

    def _post(self, path, body, trace_id):
        request_id = str(trace_id)
        started = time.monotonic()
        try:
            with self.client.stream(
                "POST",
                path,
                headers={"X-Road-Client": self.settings.xroad_client, "X-Road-Id": request_id},
                json=body,
            ) as response:
                if response.status_code == 404:
                    raise UpstreamError("XR_NOT_FOUND")
                if response.status_code != 200:
                    raise UpstreamError("XR_UNAVAILABLE")
                if response.headers.get("X-Mock-Service") != "true":
                    raise UpstreamError("XR_INVALID_RESPONSE")
                content = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() - started > self.settings.timeout_seconds:
                        raise UpstreamError("XR_TIMEOUT")
                    content.extend(chunk)
                    if len(content) > 131072:
                        raise UpstreamError("XR_INVALID_RESPONSE")
                import json

                try:
                    payload = json.loads(content)
                except (ValueError, UnicodeError) as exc:
                    raise UpstreamError("XR_INVALID_RESPONSE") from exc
                return payload
        except httpx.TimeoutException as exc:
            raise UpstreamError("XR_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("XR_UNAVAILABLE") from exc
