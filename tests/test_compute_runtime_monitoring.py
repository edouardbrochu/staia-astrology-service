"""Monitoring tests for astrology compute runtime warnings."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from app.infrastructure.compute_runtime import AstrologyComputeRuntime


def _patch_process_pool(monkeypatch) -> dict[str, object]:
    created: dict[str, object] = {}

    def fake_get_context(method: str):
        created["method"] = method
        return SimpleNamespace(name=method)

    class FakeProcessPoolExecutor:
        def __init__(self, *, max_workers: int, mp_context) -> None:
            created["max_workers"] = max_workers
            created["mp_context"] = mp_context

        def shutdown(self, wait: bool = True) -> None:
            created["shutdown_wait"] = wait

    monkeypatch.setattr("app.infrastructure.compute_runtime.multiprocessing.get_context", fake_get_context)
    monkeypatch.setattr("app.infrastructure.compute_runtime.ProcessPoolExecutor", FakeProcessPoolExecutor)
    return created


def test_runtime_uses_spawned_process_pool(monkeypatch) -> None:
    created = _patch_process_pool(monkeypatch)

    runtime = AstrologyComputeRuntime(max_workers=3)
    runtime.shutdown()

    assert created["method"] == "spawn"
    assert created["max_workers"] == 3
    assert created["mp_context"] == SimpleNamespace(name="spawn")
    assert created["shutdown_wait"] is True


def test_compute_pressure_is_logged_not_sent_to_sentry(monkeypatch, caplog) -> None:
    _patch_process_pool(monkeypatch)
    runtime = AstrologyComputeRuntime(max_workers=2)

    with caplog.at_level(logging.WARNING, logger="app.infrastructure.compute_runtime"):
        runtime._report_queue_pressure(
            route_name="/api/v1/astrology/profile",
            task_name="profile_compact",
            queue_wait_ms=500.0,
            execution_ms=200.0,
            total_ms=700.0,
        )
        runtime._report_slow_task(
            route_name="/api/v1/astrology/profile/placements",
            task_name="placements",
            queue_wait_ms=100.0,
            execution_ms=4100.0,
            total_ms=4200.0,
        )
    runtime.shutdown()

    assert [record.getMessage() for record in caplog.records] == [
        "Astrology compute queue pressure route=/api/v1/astrology/profile task=profile_compact "
        "queue_wait_ms=500.0 execution_ms=200.0 total_ms=700.0 compute_pool_size=2",
        "Astrology compute slow task route=/api/v1/astrology/profile/placements task=placements "
        "queue_wait_ms=100.0 execution_ms=4100.0 total_ms=4200.0 compute_pool_size=2",
    ]
