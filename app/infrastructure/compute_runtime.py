"""Shared bounded process-pool execution for astrology tasks."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from fastapi import Request

from app.application.compatibility_service import SynastryService
from app.application.profile_service import ProfileService
from app.application.transit_period_service import TransitPeriodService
from app.config.astrology_presets import DetailLevel, get_preset
from app.config.chart_system import HouseSystem, Zodiac, chart_system_config
from app.config.constants import (
    ASTROLOGY_COMPUTE_QUEUE_WARNING_MS,
    ASTROLOGY_COMPUTE_TOTAL_WARNING_MS,
)
from app.config.settings import Settings, settings
from app.core.exceptions import ChartCalculationException, InvalidBirthDataException
from app.infrastructure.providers.kerykeion_provider import KerykeionProvider
from app.models.requests import ChartSystemRequest, ProfileRequest, SynastryRequest, TransitPeriodRequest

logger = logging.getLogger(__name__)

_WORKER_SERVICES: dict[tuple[Zodiac, HouseSystem], dict[str, Any]] = {}


def _get_worker_services(chart_system: ChartSystemRequest) -> dict[str, Any]:
    """Lazily initialize astrology services once per chart system and executor worker process."""
    key = (chart_system.zodiac, chart_system.house_system)
    if key not in _WORKER_SERVICES:
        provider = KerykeionProvider(
            config=get_preset(DetailLevel.CORE),
            chart_system=chart_system_config(chart_system.zodiac, chart_system.house_system),
        )
        _WORKER_SERVICES[key] = {
            "profile": ProfileService(provider=provider),
            "synastry": SynastryService(provider=provider),
            "transit_period": TransitPeriodService(provider=provider),
        }
    return _WORKER_SERVICES[key]


def _run_compute_task(task_name: str, payload: dict[str, Any], enqueued_at: float) -> dict[str, Any]:
    """Execute a serializable astrology task inside the shared worker pool."""
    started_at = time.time()
    try:
        if task_name == "profile_compact":
            request = ProfileRequest.model_validate(payload)
            result = _get_worker_services(request.chart_system)["profile"].generate_profile_compact(request, request.transit_date)
        elif task_name == "lookup_profile_compact":
            request = ProfileRequest.model_validate(payload)
            result = _get_worker_services(request.chart_system)["profile"].generate_personal_profile_compact(
                request,
                request.transit_date,
                subject_label=request.subject_label,
            )
        elif task_name == "placements":
            request = ProfileRequest.model_validate(payload)
            result = _get_worker_services(request.chart_system)["profile"].generate_placements(request).model_dump(mode="json")
        elif task_name == "synastry_compact":
            request = SynastryRequest.model_validate(payload)
            result = _get_worker_services(request.chart_system)["synastry"].analyze_synastry_compact(
                request.person1,
                request.person2,
                person1_label=request.person1_label,
                person2_label=request.person2_label,
            )
        elif task_name == "transit_period_compact":
            request = TransitPeriodRequest.model_validate(payload)
            result = _get_worker_services(request.chart_system)["transit_period"].generate_transit_period_compact(
                request,
                request.start_date,
                request.end_date,
                subject_label=request.subject_label,
            )
        else:
            raise ValueError(f"Unknown astrology compute task: {task_name}")

        finished_at = time.time()
        return {
            "ok": True,
            "result": result,
            "queue_wait_ms": (started_at - enqueued_at) * 1000,
            "execution_ms": (finished_at - started_at) * 1000,
        }
    except Exception as exc:
        finished_at = time.time()
        return {
            "ok": False,
            "exception_type": exc.__class__.__name__,
            "message": str(exc),
            "queue_wait_ms": (started_at - enqueued_at) * 1000,
            "execution_ms": (finished_at - started_at) * 1000,
        }


class AstrologyComputeRuntime:
    """Shared bounded process-pool runtime for astrology work."""

    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers
        self._executor = ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=multiprocessing.get_context("spawn"),
        )

    async def run(self, task_name: str, payload: dict[str, Any], route_name: str) -> Any:
        """Execute a task and log queue, execution, and total duration."""
        enqueued_at = time.time()
        total_started = time.perf_counter()
        try:
            loop = asyncio.get_running_loop()
            envelope = await loop.run_in_executor(
                self._executor,
                _run_compute_task,
                task_name,
                payload,
                enqueued_at,
            )
        except Exception:
            total_ms = (time.perf_counter() - total_started) * 1000
            logger.exception(
                "Astrology compute task crashed route=%s task=%s total_ms=%.1f success=false",
                route_name,
                task_name,
                total_ms,
            )
            raise

        total_ms = (time.perf_counter() - total_started) * 1000
        if envelope["ok"]:
            logger.info(
                "Astrology compute task completed route=%s task=%s queue_wait_ms=%.1f execution_ms=%.1f total_ms=%.1f success=true",
                route_name,
                task_name,
                envelope["queue_wait_ms"],
                envelope["execution_ms"],
                total_ms,
            )
            self._report_queue_pressure(
                route_name=route_name,
                task_name=task_name,
                queue_wait_ms=envelope["queue_wait_ms"],
                execution_ms=envelope["execution_ms"],
                total_ms=total_ms,
            )
            self._report_slow_task(
                route_name=route_name,
                task_name=task_name,
                queue_wait_ms=envelope["queue_wait_ms"],
                execution_ms=envelope["execution_ms"],
                total_ms=total_ms,
            )
            return envelope["result"]

        logger.warning(
                "Astrology compute task failed route=%s task=%s queue_wait_ms=%.1f execution_ms=%.1f total_ms=%.1f success=false error_type=%s",
                route_name,
                task_name,
            envelope["queue_wait_ms"],
            envelope["execution_ms"],
            total_ms,
            envelope["exception_type"],
        )
        raise _restore_exception(envelope["exception_type"], envelope["message"])

    def _report_queue_pressure(
        self,
        *,
        route_name: str,
        task_name: str,
        queue_wait_ms: float,
        execution_ms: float,
        total_ms: float,
    ) -> None:
        if queue_wait_ms < ASTROLOGY_COMPUTE_QUEUE_WARNING_MS:
            return
        logger.warning(
            "Astrology compute queue pressure route=%s task=%s queue_wait_ms=%.1f execution_ms=%.1f total_ms=%.1f compute_pool_size=%s",
            route_name,
            task_name,
            queue_wait_ms,
            execution_ms,
            total_ms,
            self.max_workers,
        )

    def _report_slow_task(
        self,
        *,
        route_name: str,
        task_name: str,
        queue_wait_ms: float,
        execution_ms: float,
        total_ms: float,
    ) -> None:
        if total_ms < ASTROLOGY_COMPUTE_TOTAL_WARNING_MS:
            return
        logger.warning(
            "Astrology compute slow task route=%s task=%s queue_wait_ms=%.1f execution_ms=%.1f total_ms=%.1f compute_pool_size=%s",
            route_name,
            task_name,
            queue_wait_ms,
            execution_ms,
            total_ms,
            self.max_workers,
        )

    def shutdown(self) -> None:
        """Shut down the shared worker pool."""
        self._executor.shutdown(wait=True)


def _restore_exception(exception_type: str, message: str) -> Exception:
    """Reconstruct common astrology exceptions in the main process."""
    if exception_type == "InvalidBirthDataException":
        return InvalidBirthDataException(message)
    if exception_type == "ChartCalculationException":
        return ChartCalculationException(message)
    if exception_type == "ValueError":
        return ValueError(message)
    return RuntimeError(message)


def create_compute_runtime(settings: Settings) -> AstrologyComputeRuntime:
    """Create the shared compute runtime from settings."""
    logger.info(
        "Initializing astrology compute runtime with %s worker process(es)",
        settings.compute_pool_size,
    )
    return AstrologyComputeRuntime(max_workers=settings.compute_pool_size)


def get_compute_runtime(request: Request) -> AstrologyComputeRuntime:
    """Get shared astrology compute runtime from FastAPI app state."""
    runtime = getattr(request.app.state, "astrology_compute_runtime", None)
    if runtime is None:
        runtime = create_compute_runtime(settings)
        request.app.state.astrology_compute_runtime = runtime
    return runtime
