"""Tests for astrology-service Sentry init."""

import logging
from unittest.mock import patch

import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from app.main import init_astrology_sentry


class _CapturingTransport(Transport):
    def __init__(self):
        super().__init__()
        self.items = []

    def capture_envelope(self, envelope):
        self.items.extend(envelope.items)


def test_astrology_sentry_reports_errors_without_logs_or_private_request_data():
    transport = _CapturingTransport()
    real_init = sentry_sdk.init
    with patch(
        "app.main.sentry_sdk.init",
        side_effect=lambda **kwargs: real_init(transport=transport, **kwargs),
    ):
        init_astrology_sentry(
            dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
            environment="prod-astrology",
            release="staia-astrology@1.2.3",
        )

    app = FastAPI()

    @app.post("/boom")
    async def boom(payload: dict):
        logging.getLogger("astrology.test").error("logged failure")
        raise RuntimeError("chart failed")

    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/boom",
            json={"birth_date": "1990-01-01"},
            headers={"Authorization": "bearer-key", "X-Forwarded-For": "203.0.113.9"},
        )
        sentry_sdk.flush()
    finally:
        sentry_sdk.init(dsn=None)

    assert response.status_code == 500
    assert not [item for item in transport.items if item.type == "log"]
    events = [item.payload.json for item in transport.items if item.type == "event"]
    assert len(events) == 1
    assert events[0]["exception"]["values"][-1]["type"] == "RuntimeError"
    request = events[0]["request"]
    assert "data" not in request
    assert request["headers"]["authorization"] == "[Filtered]"
    assert request["headers"]["x-forwarded-for"] == "[Filtered]"
