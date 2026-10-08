"""Output policy for astrology requests with unknown birth time or location."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.models import BirthData, NatalChart
from app.domain.ports import IAstrologyProvider

CORE_NATAL_BODIES = (
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
    "chiron",
)


def has_unknown_birth_data(birth_data: BirthData) -> bool:
    """Return whether birth time or location is not user-backed."""
    return not birth_data.birth_time_known or not birth_data.birth_location_known


def filtered_natal_note(birth_data: BirthData, label: str | None) -> str:
    """Build the filtered-output note for natal chart partial mode."""
    return (
        f"NOTE: {_unknown_phrase(birth_data)} for {_clean_label(label, 'the subject')} is unknown; "
        "ascendant, houses, house placements, points, exact degrees, aspects, transit aspects, "
        "and exact orbs were omitted."
    )


def synastry_caution_note(affected: list[tuple[BirthData, str | None]]) -> str:
    """Build the synastry caution note for one or more affected people."""
    subjects = [
        f"{_unknown_phrase(birth_data)} for {_clean_label(label, fallback)} is unknown"
        for birth_data, label, fallback in _with_fallbacks(affected)
    ]
    return f"NOTE: {'; '.join(subjects)}; some time-sensitive synastry may be less precise."


def transit_caution_note(birth_data: BirthData, label: str | None) -> str:
    """Build the transit-period caution note."""
    return (
        f"NOTE: {_unknown_phrase(birth_data)} for {_clean_label(label, 'the subject')} is unknown; "
        "exact transit timing may be less precise."
    )


def prepend_note_after_chart_system(text: str, note: str) -> str:
    """Insert a note directly below CHART_SYSTEM when present."""
    lines = text.splitlines()
    if lines and lines[0].startswith("CHART_SYSTEM:"):
        return "\n".join([lines[0], note, *lines[1:]]).strip()
    return "\n".join([note, text]).strip()


def format_safe_partial_natal_chart(
    *,
    provider: IAstrologyProvider,
    birth_data: BirthData,
    subject_label: str | None,
) -> str:
    """Format a heavily filtered natal chart for unknown birth time/location."""
    stable_chart = _stable_natal_chart(provider=provider, birth_data=birth_data)
    lines = _chart_system_lines(stable_chart["chart_system"])
    lines.append(filtered_natal_note(birth_data, subject_label))

    stable_planets = stable_chart["planets"]
    if stable_planets:
        lines.append("")
        lines.append("PLANETS")
        lines.extend(stable_planets)
    return "\n".join(lines).strip()


def _stable_natal_chart(provider: IAstrologyProvider, birth_data: BirthData) -> dict[str, Any]:
    start_birth_data, end_birth_data = _uncertainty_boundary_birth_data(birth_data)
    start_chart = provider.calculate_natal_chart(start_birth_data)
    end_chart = provider.calculate_natal_chart(end_birth_data)

    lines: list[str] = []
    for body in CORE_NATAL_BODIES:
        start_body = _body_data(start_chart, body)
        end_body = _body_data(end_chart, body)
        if not start_body or not end_body:
            continue
        start_sign = start_body.get("sign")
        if start_sign and start_sign == end_body.get("sign"):
            lines.append(f"{_display_name(start_body, body)} in {start_sign}")
    return {"chart_system": start_chart.chart_system, "planets": lines}


def _uncertainty_boundary_birth_data(birth_data: BirthData) -> tuple[BirthData, BirthData]:
    birth_date = date(birth_data.year, birth_data.month, birth_data.day)
    if not birth_data.birth_time_known and birth_data.birth_location_known:
        zone = _zoneinfo_or_utc(birth_data.timezone)
        start_local = datetime.combine(birth_date, time.min, tzinfo=zone)
        end_local = datetime.combine(birth_date + timedelta(days=1), time.min, tzinfo=zone)
        return (
            _birth_data_at_utc(birth_data, start_local.astimezone(UTC)),
            _birth_data_at_utc(birth_data, end_local.astimezone(UTC)),
        )

    if birth_data.birth_time_known and not birth_data.birth_location_known:
        local_time = time(
            birth_data.hour if birth_data.hour is not None else 12,
            birth_data.minute if birth_data.minute is not None else 0,
        )
        earliest = datetime.combine(birth_date, local_time, tzinfo=timezone(timedelta(hours=14)))
        latest = datetime.combine(birth_date, local_time, tzinfo=timezone(timedelta(hours=-12)))
        return (
            _birth_data_at_utc(birth_data, earliest.astimezone(UTC)),
            _birth_data_at_utc(birth_data, latest.astimezone(UTC)),
        )

    earliest = datetime.combine(birth_date, time.min, tzinfo=timezone(timedelta(hours=14)))
    latest = datetime.combine(birth_date + timedelta(days=1), time.min, tzinfo=timezone(timedelta(hours=-12)))
    return (
        _birth_data_at_utc(birth_data, earliest.astimezone(UTC)),
        _birth_data_at_utc(birth_data, latest.astimezone(UTC)),
    )


def _birth_data_at_utc(template: BirthData, instant: datetime) -> BirthData:
    return template.model_copy(
        update={
            "year": instant.year,
            "month": instant.month,
            "day": instant.day,
            "hour": instant.hour,
            "minute": instant.minute,
            "latitude": template.latitude or 51.5074,
            "longitude": template.longitude if template.longitude is not None else -0.1278,
            "timezone": "Etc/UTC",
            "birth_time_known": True,
            "birth_location_known": True,
        }
    )


def _body_data(chart: NatalChart, body: str) -> dict[str, Any] | None:
    body_data = chart.planets.get(body)
    return body_data if isinstance(body_data, dict) else None


def _chart_system_lines(chart_system: dict[str, Any]) -> list[str]:
    chart_system_id = chart_system.get("id")
    if chart_system_id:
        return [f"CHART_SYSTEM: {chart_system_id}"]
    return []


def _unknown_phrase(birth_data: BirthData) -> str:
    if not birth_data.birth_time_known and not birth_data.birth_location_known:
        return "birth time and birth location"
    if not birth_data.birth_time_known:
        return "birth time"
    return "birth location"


def _clean_label(label: str | None, fallback: str) -> str:
    if isinstance(label, str) and label.strip():
        return label.strip()
    return fallback


def _with_fallbacks(affected: list[tuple[BirthData, str | None]]) -> list[tuple[BirthData, str | None, str]]:
    return [
        (birth_data, label, f"Person{index}")
        for index, (birth_data, label) in enumerate(affected, start=1)
    ]


def _display_name(body_data: dict[str, Any], fallback: str) -> str:
    name = body_data.get("name")
    if isinstance(name, str) and name.strip():
        return name.replace("_", " ")
    return fallback.replace("_", " ").title()


def _zoneinfo_or_utc(timezone_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")
