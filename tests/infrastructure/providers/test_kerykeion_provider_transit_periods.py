"""Transit periods over short and long date ranges."""

from __future__ import annotations

import re
import time

from app.infrastructure.compute_runtime import _run_compute_task

ME = {"year": 1994, "month": 8, "day": 12, "hour": 21, "minute": 40, "latitude": 51.5074, "longitude": -0.1278, "timezone": "Europe/London"}
CHART_SYSTEM = {"zodiac": "western", "house_system": "placidus"}
TRANSIT_LINE = re.compile(r"^(?P<key>\w+ \w+ \w+): (?P<range>\S+) exact (?P<exact>\S+) \(")


def _transits(start: str, end: str) -> list[dict[str, str]]:
    payload = {**ME, "start_date": start, "end_date": end, "chart_system": CHART_SYSTEM}
    outcome = _run_compute_task("transit_period_compact", payload, time.time())
    assert outcome["ok"], outcome
    return [m.groupdict() for line in outcome["result"].splitlines() if (m := TRANSIT_LINE.match(line))]


def _keys(transits: list[dict[str, str]]) -> set[str]:
    return {t["key"] for t in transits}


def test_a_single_day_lists_the_transits_active_that_day():
    day = _transits("2026-11-16", "2026-11-16")

    assert "Mars sq Pluto" in _keys(day)  # exact that day (0.7°)
    assert all(t["range"] == "Nov16-16" and t["exact"] == "Nov16" for t in day)


def test_a_week_keeps_transits_active_the_whole_week():
    week = _transits("2026-11-16", "2026-11-22")
    month = _transits("2026-11-16", "2026-12-15")

    # Active all week, so the old 80% background rule dropped them from the week.
    assert {"Mars sq Pluto", "Venus sq Uranus"} <= _keys(week)
    # Every month transit that peaks inside the week is in the week too.
    peaks_in_week = {f"Nov{day}" for day in range(16, 23)}
    assert _keys([t for t in month if t["exact"] in peaks_in_week]) <= _keys(week)


def test_a_long_period_still_skips_background_transits():
    month = _transits("2026-11-16", "2026-12-15")

    # Uranus trine Venus runs the whole month: background for a month, so skipped.
    assert "Uranus tri Venus" not in _keys(month)


def test_a_transit_that_comes_back_is_a_separate_period_each_time():
    year = [t for t in _transits("2027-01-01", "2027-12-31") if t["key"] == "Sun sq Sun"]

    # The Sun squares the natal Sun twice a year, about six months apart: two
    # periods, each starting and peaking in its own month, not one May-Nov span.
    assert [t["exact"][:3] for t in year] == ["May", "Nov"]
    assert [t["range"][:3] for t in year] == ["May", "Nov"]
