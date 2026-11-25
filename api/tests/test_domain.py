"""Unit tests for source translation, validation and safe configuration."""

from datetime import date

import pytest
from pydantic import ValidationError

from licence_api.config import Settings
from licence_api.models import PreferencesInput
from licence_api.upstream import UpstreamError, parse_source


def valid_source():
    return {
        "staatus": "kehtiv",
        "loaTyyp": "JUHILUBA",
        "valjastamisKp": "01.06.2020",
        "juhtimisOiguseLoppKp": "01.06.2030",
        "isikukood": "00000000001",
        "eesnimi": "Test",
        "loaNr": "MOCK0001",
        "kategooriad": [
            {"kood": "B", "esmakordseValjastamiseKp": "01.06.2015", "kehtivusKp": "01.06.2030"}
        ],
    }


def test_minimizes_source_and_preserves_category_dates():
    observed = parse_source(valid_source(), "trace")
    assert observed.expires_on == date(2030, 6, 1)
    assert observed.categories == (("B", date(2015, 6, 1), date(2030, 6, 1)),)
    assert not hasattr(observed, "isikukood")
    assert not hasattr(observed, "loaNr")


@pytest.mark.parametrize(
    "mutator",
    [
        lambda x: x.pop("kategooriad"),
        lambda x: x.update(juhtimisOiguseLoppKp="bad-date"),
        lambda x: x.update(valjastamisKp="01.06.2040"),
        lambda x: x.update(staatus="unexpected"),
        lambda x: x.update(loaTyyp="unknown"),
        lambda x: x["kategooriad"][0].update(kood="???"),
        lambda x: x["kategooriad"].append(x["kategooriad"][0]),
    ],
)
def test_rejects_incomplete_or_inconsistent_source(mutator):
    payload = valid_source()
    mutator(payload)
    with pytest.raises(UpstreamError, match="XR_INVALID_RESPONSE"):
        parse_source(payload, "trace")


def test_invalid_source_does_not_invent_documents():
    observed = parse_source(
        {"staatus": "kehtetu", "pohjuseKood": "JUHTIMISOIGUS_EI_OLE_KEHTIV"}, "trace"
    )
    assert observed.status == "invalid"
    assert observed.expires_on is None and observed.categories == ()


@pytest.mark.parametrize("intervals", [[14], [7, 7], [True], ["7"], [7, 30, 90, 1]])
def test_rejects_invalid_reminder_choices(intervals):
    with pytest.raises(ValidationError):
        PreferencesInput(enabled=True, intervals=intervals)


def test_preferences_normalize_order():
    assert PreferencesInput(enabled=True, intervals=[7, 90]).intervals == [90, 7]


def test_mock_deployment_cannot_start_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="mock X-Road"):
        Settings.from_env()
