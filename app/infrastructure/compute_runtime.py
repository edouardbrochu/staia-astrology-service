"""Shared bounded process-pool execution for astrology tasks."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from time import monotonic
from typing import Any

import sentry_sdk
from fastapi import Request

from app.application.compatibility_service import SynastryService
from app.application.profile_service import ProfileService
from app.application.transit_period_service import TransitPeriodService
from app.config.astrology_presets import DetailLevel, get_preset
from app.config.chart_system import DEFAULT_CHART_SYSTEM
from app.config.constants import (
    ASTROLOGY_COMPUTE_QUEUE_WARNING_MS,
    ASTROLOGY_COMPUTE_TOTAL_WARNING_MS,
    ASTROLOGY_COMPUTE_WARNING_COOLDOWN_SECONDS,
)
from app.config.settings import Settings, settings
from app.core.exceptions import ChartCalculationException, InvalidBirthDataException
from app.infrastructure.providers.kerykeion_provider import KerykeionProvider
from app.models.requests import ProfileRequest, SynastryRequest, TransitPeriodRequest

logger = logging.getLogger(__name__)

_WORKER_SERVICES: dict[str, Any] | None = None


def _get_worker_services() -> dict[str, Any]:
    """Lazily initialize astrology services once per executor worker process."""
    global _WORKER_SERVICES
    if _WORKER_SERVICES is None:
        provider = KerykeionProvider(
            config=get_preset(DetailLevel.CORE),
            chart_system=DEFAULT_CHART_SYSTEM,
        )
        _WORKER_SERVICES = {
            "profile": ProfileService(provider=provider),
            "synastry": SynastryService(provider=provider),
            "transit_period": TransitPeriodService(provider=provider),
        }
    return _WORKER_SERVICES


def _run_compute_task(task_name: str, payload: dict[str, Any], enqueued_at: float) -> dict[str, Any]:
    """Execute a serializable astrology task inside the shared worker pool."""
    started_at = time.time()
    try:
        services = _get_worker_services()
        if task_name == "profile_compact":
            request = ProfileRequest.model_validate(payload)
            result = services["profile"].generate_profile_compact(request, request.transit_date)
        elif task_name == "lookup_profile_compact":
            request = ProfileRequest.model_validate(payload)
            result = services["profile"].generate_personal_profile_compact(
                request,
                request.transit_date,
                subject_label=request.subject_label,
            )
        elif task_name == "placements":
            request = ProfileRequest.model_validate(payload)
            result = services["profile"].generate_placements(request).model_dump(mode="json")
        elif task_name == "synastry_compact":
            request = SynastryRequest.model_validate(payload)
            result = services["synastry"].analyze_synastry_compact(
                request.person1,
                request.person2,
                person1_label=request.person1_label,
                person2_label=request.person2_label,
            )
        elif task_name == "transit_period_compact":
            request = TransitPeriodRequest.model_validate(payload)
            result = services["transit_period"].generate_transit_period_compact(
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
        self._last_warning_ts: dict[tuple[str, str], float] = {}

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
        if not self._warning_allowed("queue_pressure", task_name):
            return

        message = (
            "Astrology compute queue pressure detected "
            f"(task={task_name}, route={route_name}, queue_wait_ms={queue_wait_ms:.1f})"
        )
        self._capture_warning(
            message=message,
            error_type="astrology_compute_queue_pressure",
            route_name=route_name,
            task_name=task_name,
            queue_wait_ms=queue_wait_ms,
            execution_ms=execution_ms,
            total_ms=total_ms,
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
        if not self._warning_allowed("slow_task", task_name):
            return

        message = (
            "Astrology compute slow task detected "
            f"(task={task_name}, route={route_name}, total_ms={total_ms:.1f})"
        )
        self._capture_warning(
            message=message,
            error_type="astrology_compute_slow_task",
            route_name=route_name,
            task_name=task_name,
            queue_wait_ms=queue_wait_ms,
            execution_ms=execution_ms,
            total_ms=total_ms,
        )

    def _warning_allowed(self, warning_type: str, task_name: str) -> bool:
        key = (warning_type, task_name)
        now = monotonic()
        last_sent = self._last_warning_ts.get(key)
        if (
            last_sent is not None
            and now - last_sent < ASTROLOGY_COMPUTE_WARNING_COOLDOWN_SECONDS
        ):
            return False
        self._last_warning_ts[key] = now
        return True

    def _capture_warning(
        self,
        *,
        message: str,
        error_type: str,
        route_name: str,
        task_name: str,
        queue_wait_ms: float,
        execution_ms: float,
        total_ms: float,
    ) -> None:
        try:
            with sentry_sdk.new_scope() as scope:
                scope.set_tag("error_type", error_type)
                scope.set_tag("service_role", "astrology-service")
                scope.set_tag("astrology_task", task_name)
                scope.set_context(
                    "astrology_compute_runtime",
                    {
                        "route": route_name,
                        "task": task_name,
                        "queue_wait_ms": queue_wait_ms,
                        "execution_ms": execution_ms,
                        "total_ms": total_ms,
                        "compute_pool_size": self.max_workers,
                    },
                )
                sentry_sdk.capture_message(message, level="warning")
        except Exception as error:
            logger.debug("Failed to report astrology compute warning to Sentry: %s", error)

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
