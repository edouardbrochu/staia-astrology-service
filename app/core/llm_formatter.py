"""LLM-optimized formatters for astrological data.

This module provides compact, word-based formatting for astrological data
to reduce token usage when passing to LLMs (~80% reduction).

Output style: "Sun in Aries 15 deg (H1, Rx)", "Sun conjunct Moon (orb 2.3)"
"""

import math
from typing import Any

# Essential fields to keep when simplifying data
ESSENTIAL_PLANET_FIELDS = {"name", "sign", "position", "house", "nakshatra", "retrograde"}
ESSENTIAL_ASPECT_FIELDS = {"p1_name", "p2_name", "aspect", "orbit"}
MAJOR_ASPECTS = {"conjunction", "opposition", "square", "trine", "sextile"}

# Bodies to exclude (redundant opposites and secondary points)
EXCLUDED_BODIES = {
    # Redundant opposite angles
    "descendant", "imum_coeli",
    # Secondary/less essential
    "mean_lilith",
}

# Outer planets (for filtering generational aspects)
OUTER_PLANETS = {"uranus", "neptune", "pluto"}

BODY_DISPLAY_NAMES = {
    "medium_coeli": "Midheaven",
    "imum_coeli": "Imum Coeli",
    "true_north_lunar_node": "North Node",
    "mean_north_lunar_node": "North Node",
    "true_south_lunar_node": "South Node",
    "mean_south_lunar_node": "South Node",
}


def _normalize_body_key(name: Any) -> str:
    """Normalize provider body names to a stable snake_case key."""
    return str(name).strip().lower().replace(" ", "_")


def _format_body_name(name: Any) -> str:
    """Humanize provider body names for compact prompt text."""
    raw_name = str(name).strip()
    normalized = _normalize_body_key(raw_name)
    if normalized in BODY_DISPLAY_NAMES:
        return BODY_DISPLAY_NAMES[normalized]
    if "_" not in raw_name:
        return raw_name
    return " ".join(part.capitalize() for part in normalized.split("_"))


def _chart_system_header(data: dict[str, Any]) -> list[str]:
    """Format chart-system metadata as a compact header line."""
    chart_system = data.get("chart_system", {})
    chart_system_id = chart_system.get("id")
    if not chart_system_id:
        return []
    return [f"CHART_SYSTEM: {chart_system_id}", ""]


def simplify_planets(planets: dict[str, Any]) -> dict[str, Any]:
    """Keep only essential planet fields for LLM consumption.

    Removes technical fields that don't improve LLM interpretation:
    - speed, declination (technical data)
    - element, quality, sign_num, abs_pos (redundant - inferred from sign)

    Args:
        planets: Full planet data dictionary from astrology provider

    Returns:
        Simplified planet data with essential fields only
    """
    simplified = {}
    for planet_key, planet_data in planets.items():
        if isinstance(planet_data, dict):
            simplified[planet_key] = {
                k: v for k, v in planet_data.items()
                if k in ESSENTIAL_PLANET_FIELDS
            }
        else:
            # Non-dict values (like birth_data) pass through unchanged
            simplified[planet_key] = planet_data
    return simplified


def filter_aspects(aspects: list[dict], filter_generational: bool = True) -> list[dict]:
    """Filter aspects using smart rules to reduce tokens while preserving accuracy.

    Filtering rules:
    1. Major aspects only (conjunction, opposition, square, trine, sextile)
    2. Exclude redundant opposite angles (Descendant, IC)
    3. Exclude secondary bodies (Mean_Lilith)
    4. Optionally exclude generational outer-to-outer aspects (Uranus-Neptune-Pluto)

    NO orb filtering - all orbs included so LLM can assess aspect strength.

    Args:
        aspects: List of aspect dictionaries from astrology provider
        filter_generational: If True, remove outer-to-outer natal aspects (default True)

    Returns:
        Filtered list of major aspects with essential fields only
    """
    filtered = []
    for aspect in aspects:
        aspect_name = aspect.get("aspect", "").lower()
        p1 = _normalize_body_key(aspect.get("p1_name", ""))
        p2 = _normalize_body_key(aspect.get("p2_name", ""))

        # Skip non-major aspects
        if aspect_name not in MAJOR_ASPECTS:
            continue

        # Skip if either body is in excluded list
        if p1 in EXCLUDED_BODIES or p2 in EXCLUDED_BODIES:
            continue

        # Skip generational outer-to-outer aspects (optional)
        if filter_generational and p1 in OUTER_PLANETS and p2 in OUTER_PLANETS:
            continue

        # Keep only essential fields
        filtered.append({
            k: v for k, v in aspect.items()
            if k in ESSENTIAL_ASPECT_FIELDS
        })

    return filtered


# House name to number mapping
HOUSE_NAME_TO_NUM = {
    "first_house": 1, "second_house": 2, "third_house": 3, "fourth_house": 4,
    "fifth_house": 5, "sixth_house": 6, "seventh_house": 7, "eighth_house": 8,
    "ninth_house": 9, "tenth_house": 10, "eleventh_house": 11, "twelfth_house": 12,
}


def _normalize_house(house: Any) -> str | None:
    """Convert house value to compact format (H1-H12)."""
    if house is None:
        return None
    if isinstance(house, int):
        return f"H{house}"
    # Handle string house names like "Eighth_House" or "eighth_house"
    house_lower = str(house).lower().replace(" ", "_")
    if house_lower in HOUSE_NAME_TO_NUM:
        return f"H{HOUSE_NAME_TO_NUM[house_lower]}"
    # Fallback: just use the value
    return f"H{house}"


def format_planet(planet: dict[str, Any]) -> str:
    """Format a single planet as word-based compact text.

    Args:
        planet: Planet dictionary with name, sign, position, house, optional nakshatra, retrograde

    Returns:
        Formatted string like "Sun in Aries 15 deg (H1)", "Mercury in Pisces 8 deg (H12, Rx)",
        or, in sidereal charts, "Moon in Libra 14 deg (H4, Swati 3)"
    """
    name = _format_body_name(planet.get("name", "Unknown"))
    sign = planet.get("sign", "Unknown")
    position = planet.get("position", 0)
    house = planet.get("house")
    retrograde = planet.get("retrograde", False)

    # Format position as integer degrees
    pos_str = f"{int(position)}°"

    # Build house and retrograde suffix
    suffixes = []
    house_str = _normalize_house(house)
    if house_str:
        suffixes.append(house_str)
    if planet.get("nakshatra"):
        suffixes.append(planet["nakshatra"])
    if retrograde:
        suffixes.append("Rx")

    suffix = f" ({', '.join(suffixes)})" if suffixes else ""

    return f"{name} in {sign} {pos_str}{suffix}"


def format_aspect(aspect: dict[str, Any], prefix1: str = "", prefix2: str = "") -> str:
    """Format an aspect as word-based compact text.

    Args:
        aspect: Aspect dictionary with p1_name, p2_name, aspect, orbit
        prefix1: Optional prefix for first planet (e.g., "Transit " or "Person1 ")
        prefix2: Optional prefix for second planet (e.g., "natal " or "Person2 ")

    Returns:
        Formatted string like "Sun conjunct Moon (orb 2.3)"
    """
    p1 = _format_body_name(aspect.get("p1_name", "Unknown"))
    p2 = _format_body_name(aspect.get("p2_name", "Unknown"))
    aspect_type = aspect.get("aspect", "aspect").lower()
    orbit = aspect.get("orbit", 0)

    return f"{prefix1}{p1} {aspect_type} {prefix2}{p2} (orb {abs(orbit):.1f})"


def _find_natal_house(abs_pos: float, natal_houses: dict[str, Any]) -> int | None:
    """Find which natal house a planet falls in based on ecliptic position.

    Args:
        abs_pos: Absolute ecliptic position (0-360 degrees)
        natal_houses: Natal houses dict with house_name -> {abs_pos, ...}

    Returns:
        House number (1-12) or None if houses lack abs_pos data
    """
    cusps: list[tuple[int, float]] = []
    for house_name, house_data in natal_houses.items():
        if not isinstance(house_data, dict):
            continue
        house_num = HOUSE_NAME_TO_NUM.get(house_name.lower().replace(" ", "_"))
        house_pos = house_data.get("abs_pos")
        if house_num is not None and house_pos is not None:
            cusps.append((house_num, float(house_pos)))
    if not cusps:
        return None
    cusps.sort(key=lambda c: c[1])
    for i in range(len(cusps)):
        current_num, current_pos = cusps[i]
        next_pos = cusps[(i + 1) % len(cusps)][1]
        if next_pos <= current_pos:
            # Wrap-around: next cusp is past 360
            if abs_pos >= current_pos or abs_pos < next_pos:
                return current_num
        else:
            if current_pos <= abs_pos < next_pos:
                return current_num
    return cusps[-1][0]


def _format_transit_body(body_data: dict[str, Any], natal_houses: dict[str, Any]) -> str:
    """Format a transit body with corrected natal house placement.

    If abs_pos and natal houses are available, computes the correct natal house.
    Otherwise strips the house entirely (better none than wrong).

    Args:
        body_data: Transit body data dict
        natal_houses: Natal chart houses dict

    Returns:
        Formatted body string with corrected house
    """
    abs_pos = body_data.get("abs_pos")
    if abs_pos is not None and natal_houses:
        natal_house = _find_natal_house(float(abs_pos), natal_houses)
        if natal_house is not None:
            corrected = {**body_data, "house": natal_house}
            return format_planet(corrected)
    # Strip house entirely — better no house than wrong house
    stripped = {**body_data, "house": None}
    return format_planet(stripped)


def _format_natal_sections(chart_data: dict[str, Any]) -> list[str]:
    """Format the common natal chart sections: planets, points, houses, natal aspects.

    Shared by format_natal_chart and format_personal_profile.

    Args:
        chart_data: Chart data with natal_chart and aspects keys

    Returns:
        List of formatted lines (with trailing blank lines per section)
    """
    lines = []
    natal_chart = chart_data.get("natal_chart", {})

    # Planets
    planets = natal_chart.get("planets", {})
    if planets:
        lines.append("PLANETS")
        for planet_key, planet_data in planets.items():
            if isinstance(planet_data, dict) and "name" in planet_data:
                lines.append(format_planet(planet_data))
        lines.append("")

    # Points (Ascendant, MC, etc.)
    points = natal_chart.get("points", {})
    if points:
        lines.append("POINTS")
        for point_key, point_data in points.items():
            if isinstance(point_data, dict) and "name" in point_data:
                lines.append(format_planet(point_data))
        lines.append("")

    # Houses
    houses = natal_chart.get("houses", {})
    if houses:
        lines.append("HOUSES")
        for house_key, house_data in houses.items():
            if isinstance(house_data, dict):
                name = house_data.get("name", house_key)
                sign = house_data.get("sign", "Unknown")
                lines.append(f"{name}: {sign}")
        lines.append("")

    # Natal aspects
    aspects = chart_data.get("aspects", {})
    natal_aspects = aspects.get("natal", [])
    if natal_aspects:
        filtered = filter_aspects(natal_aspects)
        if filtered:
            lines.append("NATAL ASPECTS")
            for aspect in filtered:
                lines.append(format_aspect(aspect))
            lines.append("")

    return lines


def _format_transit_to_natal_aspects(chart_data: dict[str, Any]) -> list[str]:
    """Format transit-to-natal aspects section.

    Shared by format_natal_chart and format_personal_profile.

    Args:
        chart_data: Chart data with aspects.transits_to_natal key

    Returns:
        List of formatted lines
    """
    lines = []
    aspects = chart_data.get("aspects", {})
    transit_aspects = aspects.get("transits_to_natal", [])
    if transit_aspects:
        # Don't filter generational - transiting Pluto to natal Neptune IS personal
        filtered = filter_aspects(transit_aspects, filter_generational=False)
        if filtered:
            lines.append("TRANSIT ASPECTS TO NATAL")
            for aspect in filtered:
                lines.append(format_aspect(aspect, prefix1="Transit ", prefix2="natal "))
            lines.append("")
    return lines


def format_natal_chart(chart_data: dict[str, Any]) -> str:
    """Format a complete natal chart as LLM-optimized text.

    Args:
        chart_data: Natal chart data with planets, houses, points, aspects

    Returns:
        Multi-line formatted text block
    """
    lines = _chart_system_header(chart_data)
    lines.extend(_format_natal_sections(chart_data))

    # Current transits with corrected natal house placement
    natal_chart = chart_data.get("natal_chart", {})
    natal_houses = natal_chart.get("houses", {})
    transits = chart_data.get("transits", {})
    transit_planets = transits.get("planets", {})
    transit_points = transits.get("points", {})
    if transit_planets or transit_points:
        lines.append("CURRENT TRANSITS")
        for planet_key, planet_data in transit_planets.items():
            if isinstance(planet_data, dict) and "name" in planet_data:
                lines.append(_format_transit_body(planet_data, natal_houses))
        for point_key, point_data in transit_points.items():
            if isinstance(point_data, dict) and "name" in point_data:
                lines.append(_format_transit_body(point_data, natal_houses))
        lines.append("")

    lines.extend(_format_transit_to_natal_aspects(chart_data))

    return "\n".join(lines).strip()


def format_personal_profile(chart_data: dict[str, Any]) -> str:
    """Format natal chart + personal transit aspects, excluding current sky positions.

    Unlike format_natal_chart, this excludes CURRENT TRANSITS (planet positions today)
    since those are identical for everyone. Only includes person-specific data:
    - Natal planets, points, houses, aspects
    - Transit aspects TO natal (how today's sky affects THIS person)

    Args:
        chart_data: Natal chart data with planets, houses, points, aspects

    Returns:
        Multi-line formatted text block (excludes CURRENT TRANSITS section)
    """
    lines = _chart_system_header(chart_data)
    lines.extend(_format_natal_sections(chart_data))
    lines.extend(_format_transit_to_natal_aspects(chart_data))
    return "\n".join(lines).strip()


def format_transit_periods(transit_data: dict[str, Any]) -> str:
    """Format transit periods with precise timing as LLM-optimized text.

    Compact single-line format. Natal positions excluded (already in context).

    Args:
        transit_data: Transit period data with transit_aspects containing timing info

    Returns:
        Multi-line formatted text block optimized for LLM consumption

    Example output:
        TRANSITS 2025-01-01 to 2025-03-31
        Saturn conj natal Mars: Jan1-Mar30 exact Feb9 (0.01°)
        Mars opp natal Moon: Jan1-Mar30 exact Jan15 (0.01°)
    """
    lines = _chart_system_header(transit_data)

    # Period header (compact)
    period = transit_data.get("period", {})
    start = period.get("start", "")
    end = period.get("end", "")
    lines.append(f"TRANSITS {start} to {end}")

    # Transit aspects with timing - compact single-line format
    transit_aspects = transit_data.get("transit_aspects", [])
    for aspect in transit_aspects:
        transit_planet = aspect.get("transit_planet", "")
        natal_planet = aspect.get("natal_planet", "")
        aspect_type = aspect.get("aspect_type", "")
        start_date = aspect.get("start_date", "")
        end_date = aspect.get("end_date", "")
        exact_date = aspect.get("exact_date", "")
        exact_orb = aspect.get("exact_orb", 0)

        # Shorten aspect names
        aspect_short = _shorten_aspect(aspect_type)

        # Check if period spans multiple years
        multi_year = _spans_multiple_years(start_date, end_date)

        # Format date range compact, avoid repeating month/year
        date_range = _format_date_range(start_date, end_date)
        exact_fmt = _format_compact_date(exact_date, include_year=multi_year)

        # Single line format (no "natal" - all are transit-to-natal)
        lines.append(f"{transit_planet} {aspect_short} {natal_planet}: {date_range} exact {exact_fmt} ({exact_orb}°)")

    return "\n".join(lines).strip()


def _format_date_range(start_str: str, end_str: str) -> str:
    """Format date range, avoiding repeated month/year. Jan1-4, Jan28-Feb5, Dec25'25-Jan5'26."""
    if not start_str or not end_str:
        return ""
    try:
        from datetime import date
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)

        start_month = start.strftime("%b")
        end_month = end.strftime("%b")
        start_year = start.year % 100  # 2025 -> 25
        end_year = end.year % 100

        if start.year == end.year:
            # Same year - no year needed
            if start_month == end_month:
                # Same month: Jan1-4
                return f"{start_month}{start.day}-{end.day}"
            else:
                # Different months: Jan28-Feb5
                return f"{start_month}{start.day}-{end_month}{end.day}"
        else:
            # Different years: Dec25'25-Jan5'26
            return f"{start_month}{start.day}'{start_year}-{end_month}{end.day}'{end_year}"
    except (ValueError, AttributeError):
        return f"{start_str}-{end_str}"


def _spans_multiple_years(start_str: str, end_str: str) -> bool:
    """Check if date range spans multiple years."""
    if not start_str or not end_str:
        return False
    try:
        from datetime import date
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        return start.year != end.year
    except (ValueError, AttributeError):
        return False


def _shorten_aspect(aspect_type: str) -> str:
    """Shorten aspect name for compact output."""
    shortcuts = {
        "conjunction": "conj",
        "opposition": "opp",
        "square": "sq",
        "trine": "tri",
        "sextile": "sxt",
    }
    return shortcuts.get(aspect_type.lower(), aspect_type)


def _format_compact_date(date_str: str, include_year: bool = False) -> str:
    """Format ISO date as compact date (e.g., 'Jan5' or 'Jan5'26')."""
    if not date_str:
        return ""
    try:
        from datetime import date
        d = date.fromisoformat(date_str)
        month = d.strftime("%b")
        day = d.day
        if include_year:
            year = d.year % 100  # 2026 -> 26
            return f"{month}{day}'{year}"
        return f"{month}{day}"
    except (ValueError, AttributeError):
        return date_str


def _score_to_percentage(score: int) -> int:
    """Convert Ciro Discepolo relationship score to percentage.

    Uses square root curve to align with Kerykeion's qualitative categories:
    - 0-5 (Minimal) → 0-41%
    - 5-10 (Medium) → 41-58%
    - 10-15 (Important) → 58-71%
    - 15-20 (Very Important) → 71-82%
    - 20-30 (Exceptional) → 82-100%

    Args:
        score: Raw relationship score (typically 0-30, can exceed)

    Returns:
        Percentage value 0-100
    """
    if score <= 0:
        return 0
    return min(100, round(math.sqrt(score / 30) * 100))


def format_synastry(synastry_data: dict[str, Any]) -> str:
    """Format synastry data as LLM-optimized text.

    Args:
        synastry_data: Synastry data with cross-chart aspects and optional relationship_score

    Returns:
        Multi-line formatted text block
    """
    lines = _chart_system_header(synastry_data)

    # Add compatibility score if present
    relationship_score = synastry_data.get("relationship_score")
    if relationship_score:
        percentage = _score_to_percentage(relationship_score["score_value"])
        lines.append(f"COMPATIBILITY: {percentage}%")
        if relationship_score.get("is_destiny_sign"):
            lines.append("Destiny Sign: Yes")
        lines.append("")  # Blank line before aspects

    lines.append("SYNASTRY ASPECTS")

    synastry = synastry_data.get("synastry", {})
    aspects = synastry.get("aspects", [])

    # Don't filter generational - Person1's Pluto to Person2's Neptune IS personal
    filtered = filter_aspects(aspects, filter_generational=False)

    for aspect in filtered:
        lines.append(format_aspect(aspect, prefix1="Person1 ", prefix2="Person2 "))

    return "\n".join(lines)
