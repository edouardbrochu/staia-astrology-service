"""Route wiring tests for astrology shared-runtime execution."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.infrastructure.compute_runtime import _run_compute_task
from app.main import app, create_app

BASE_BIRTH_DATA = {
    "year": 1990,
    "month": 6,
    "day": 15,
    "hour": 14,
    "minute": 30,
    "latitude": 51.5,
    "longitude": -0.1,
    "timezone": "Europe/London",
}

CHART_SYSTEM = {"zodiac": "western", "house_system": "placidus"}
PROFILE_PAYLOAD = {**BASE_BIRTH_DATA, "chart_system": CHART_SYSTEM}

SYNASTRY_PAYLOAD = {
    "chart_system": CHART_SYSTEM,
    "person1": BASE_BIRTH_DATA,
    "person2": {
        "year": 1992,
        "month": 7,
        "day": 22,
        "hour": 8,
        "minute": 15,
        "latitude": 34.0522,
        "longitude": -118.2437,
        "timezone": "America/Los_Angeles",
    },
}

TRANSIT_PERIOD_PAYLOAD = {
    **PROFILE_PAYLOAD,
    "start_date": "2026-01-01",
    "end_date": "2026-01-31",
}

CHART_SYSTEM_RESULT = {
    "id": "western_tropical_placidus",
    "zodiac_type": "Tropical",
    "house_system": "Placidus",
    "house_system_identifier": "P",
    "perspective_type": "Apparent Geocentric",
    "provider": "kerykeion",
    "sidereal_mode": None,
}

PLACEMENTS_RESULT = {
    "sun": {"name": "Sun", "sign": "Gem", "house": 1},
    "moon": {"name": "Moon", "sign": "Tau", "house": 12},
    "ascendant": {"name": "Ascendant", "sign": "Lib", "house": None},
    "planets": [
        {"name": "Sun", "sign": "Gem", "house": 1},
        {"name": "Moon", "sign": "Tau", "house": 12},
    ],
    "chart_system": CHART_SYSTEM_RESULT,
}

class FakeRuntime:
    """Async runtime stub that records calls."""

    def __init__(self, results: dict[str, object]):
        self.results = results
        self.calls: list[tuple[str, dict, str]] = []
        self.shutdown_called = False

    async def run(self, task_name: str, payload: dict, route_name: str):
        self.calls.append((task_name, payload, route_name))
        return self.results[task_name]

    def shutdown(self) -> None:
        self.shutdown_called = True


def test_cpu_bound_routes_use_shared_compute_runtime(monkeypatch):
    fake_runtime = FakeRuntime(
        {
            "profile_compact": "profile",
            "lookup_profile_compact": "lookup",
            "placements": PLACEMENTS_RESULT,
            "synastry_compact": "synastry",
            "transit_period_compact": "transit",
        }
    )
    monkeypatch.setattr("app.main.create_compute_runtime", lambda settings: fake_runtime)
    test_app = create_app(Settings(env="dev", internal_service_token="internal-token"))
    auth_headers = {"X-Astrology-Service-Token": "internal-token"}

    routes = [
        ("/api/v1/astrology/profile", PROFILE_PAYLOAD, "profile_compact"),
        ("/api/v1/astrology/profile/lookup", PROFILE_PAYLOAD, "lookup_profile_compact"),
        ("/api/v1/astrology/profile/placements", PROFILE_PAYLOAD, "placements"),
        ("/api/v1/astrology/synastry", SYNASTRY_PAYLOAD, "synastry_compact"),
        ("/api/v1/astrology/transits/period", TRANSIT_PERIOD_PAYLOAD, "transit_period_compact"),
    ]

    with TestClient(test_app) as client:
        for route, payload, task_name in routes:
            response = client.post(route, json=payload, headers=auth_headers)
            assert response.status_code == 200, route
            assert fake_runtime.calls[-1][0] == task_name
            assert fake_runtime.calls[-1][2] == route

        removed_route = client.post(
            "/api/v1/astrology/planet-house",
            json={**BASE_BIRTH_DATA, "planet": "venus"},
            headers=auth_headers,
        )
        assert removed_route.status_code == 404

def test_lifespan_sets_astrology_service_role(monkeypatch):
    fake_runtime = FakeRuntime({})
    monkeypatch.setattr("app.main.create_compute_runtime", lambda settings: fake_runtime)

    with TestClient(app):
        assert app.state.service_role == "astrology-service"

    assert fake_runtime.shutdown_called is True


def test_compute_task_uses_requested_chart_system():
    payload = {
        **BASE_BIRTH_DATA,
        "transit_date": "2026-10-20T12:00:00Z",
        "chart_system": {"zodiac": "vedic", "house_system": "whole_sign"},
    }

    outcome = _run_compute_task("lookup_profile_compact", payload, enqueued_at=0)

    assert outcome["ok"], outcome
    lines = outcome["result"].splitlines()
    assert lines[0] == "CHART_SYSTEM: vedic_sidereal_lahiri_whole_sign"
    assert "Sun in Gem 0° (H10, Mrigashira 3)" in lines
