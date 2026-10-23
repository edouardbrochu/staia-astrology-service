"""Security tests for internal astrology-service access."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app

BASE_BIRTH_DATA = {
    "year": 1990,
    "month": 6,
    "day": 15,
    "hour": 14,
    "minute": 30,
    "latitude": 51.5,
    "longitude": -0.1,
    "timezone": "Europe/London",
    "chart_system": {"zodiac": "western", "house_system": "placidus"},
}


class FakeRuntime:
    """Async runtime stub that records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str]] = []
        self.shutdown_called = False

    async def run(self, task_name: str, payload: dict, route_name: str):
        self.calls.append((task_name, payload, route_name))
        return "profile"

    def shutdown(self) -> None:
        self.shutdown_called = True


def test_create_app_disables_docs_in_prod(monkeypatch) -> None:
    fake_runtime = FakeRuntime()
    monkeypatch.setattr("app.main.create_compute_runtime", lambda settings: fake_runtime)

    app = create_app(Settings(env="prod", internal_service_token="internal-token"))

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None

    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 404


def test_create_app_keeps_docs_in_dev(monkeypatch) -> None:
    fake_runtime = FakeRuntime()
    monkeypatch.setattr("app.main.create_compute_runtime", lambda settings: fake_runtime)

    app = create_app(Settings(env="dev", internal_service_token="internal-token"))

    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"

    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200


def test_astrology_routes_require_internal_service_token_in_prod(monkeypatch) -> None:
    fake_runtime = FakeRuntime()
    monkeypatch.setattr("app.main.create_compute_runtime", lambda settings: fake_runtime)
    app = create_app(Settings(env="prod", internal_service_token="internal-token"))
    with TestClient(app) as client:
        unauthorized = client.post("/api/v1/astrology/profile", json=BASE_BIRTH_DATA)
        assert unauthorized.status_code == 401

        authorized = client.post(
            "/api/v1/astrology/profile",
            json=BASE_BIRTH_DATA,
            headers={"X-Astrology-Service-Token": "internal-token"},
        )
        assert authorized.status_code == 200

    assert fake_runtime.calls[-1][0] == "profile_compact"


def test_astrology_routes_require_internal_service_token_in_dev(monkeypatch) -> None:
    fake_runtime = FakeRuntime()
    monkeypatch.setattr("app.main.create_compute_runtime", lambda settings: fake_runtime)
    app = create_app(Settings(env="dev", internal_service_token="internal-token"))

    with TestClient(app) as client:
        unauthorized = client.post("/api/v1/astrology/profile", json=BASE_BIRTH_DATA)
        assert unauthorized.status_code == 401

        authorized = client.post(
            "/api/v1/astrology/profile",
            json=BASE_BIRTH_DATA,
            headers={"X-Astrology-Service-Token": "internal-token"},
        )
        assert authorized.status_code == 200

    assert fake_runtime.calls[-1][0] == "profile_compact"
