"""Profile application service - orchestrates natal chart and transit calculations."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.application.chart_payloads import natal_chart_payload
from app.application.unknown_birth_data_policy import (
    format_safe_partial_natal_chart,
    has_unknown_birth_data,
)
from app.core.llm_formatter import format_natal_chart, format_personal_profile
from app.domain.models import BirthData
from app.domain.ports import IAstrologyProvider
from app.models.responses import PlacementItem, PlacementsResponse


class ProfileService:
    """
    Application service for generating astrological profiles.

    Orchestrates natal chart and transit calculations for a complete profile.
    """

    def __init__(self, provider: IAstrologyProvider):
        """
        Initialize with astrology provider.

        Args:
            provider: Astrology calculation provider (injected dependency)
        """
        self.provider = provider

    @staticmethod
    def _resolve_now_for_birth_timezone(birth_data: BirthData) -> datetime:
        """
        Resolve current datetime using the subject's timezone.

        Falls back to UTC for invalid timezone strings.
        """
        timezone_name = birth_data.timezone or "UTC"
        try:
            return datetime.now(ZoneInfo(timezone_name))
        except (ZoneInfoNotFoundError, ValueError):
            return datetime.now(UTC)

    def generate_profile(self, birth_data: BirthData, transit_date: datetime | None = None) -> dict:
        """
        Generate complete astrological profile (natal chart + transits).

        Args:
            birth_data: Birth information
            transit_date: Date for transit calculation (defaults to now)

        Returns:
            Dict containing natal chart data, natal aspects, and current transits
        """
        # Calculate natal chart
        natal_chart = self.provider.calculate_natal_chart(birth_data)

        # Calculate transits (default to now if not specified)
        if transit_date is None:
            transit_date = self._resolve_now_for_birth_timezone(birth_data)

        transits = self.provider.calculate_transits(natal_chart, transit_date)

        # Build response
        return {
            "chart_system": natal_chart.chart_system,
            "natal_chart": natal_chart_payload(natal_chart),
            "aspects": {
                "natal": natal_chart.aspects,
                "transits_to_natal": transits.aspects_to_natal,
                "current_sky": transits.current_sky_aspects
            },
            "transits": {
                "date": transits.date.isoformat(),
                "planets": transits.planets,
                "points": transits.points,
            }
        }

    def generate_profile_compact(self, birth_data: BirthData, transit_date: datetime | None = None) -> str:
        """
        Generate LLM-optimized compact astrological profile.

        Args:
            birth_data: Birth information
            transit_date: Date for transit calculation (defaults to now)

        Returns:
            Compact text format optimized for LLM consumption (~80% token reduction)
        """
        profile_data = self.generate_profile(birth_data, transit_date)
        return format_natal_chart(profile_data)

    def generate_personal_profile_compact(
        self,
        birth_data: BirthData,
        transit_date: datetime | None = None,
        *,
        subject_label: str | None = None,
    ) -> str:
        """
        Generate person-specific profile, excluding current sky positions.

        Unlike generate_profile_compact, this excludes CURRENT TRANSITS (where planets
        are today) since those are identical for everyone. Includes only person-specific
        data: natal chart + how today's transits aspect THIS person's chart.

        Use this for context providers where the same transit positions would be
        redundantly included for multiple people.

        Args:
            birth_data: Birth information
            transit_date: Date for transit calculation (defaults to now)

        Returns:
            Compact text excluding current sky positions
        """
        if has_unknown_birth_data(birth_data):
            return format_safe_partial_natal_chart(
                provider=self.provider,
                birth_data=birth_data,
                subject_label=subject_label,
            )
        profile_data = self.generate_profile(birth_data, transit_date)
        return format_personal_profile(profile_data)

    @staticmethod
    def _parse_house(house_value: str | int | None) -> int | None:
        """Parse house value from Kerykeion format to integer."""
        if house_value is None:
            return None
        if isinstance(house_value, int):
            return house_value
        # Kerykeion returns strings like "First_House", "Tenth_House", etc.
        house_map = {
            "first_house": 1, "second_house": 2, "third_house": 3,
            "fourth_house": 4, "fifth_house": 5, "sixth_house": 6,
            "seventh_house": 7, "eighth_house": 8, "ninth_house": 9,
            "tenth_house": 10, "eleventh_house": 11, "twelfth_house": 12,
        }
        return house_map.get(str(house_value).lower())

    def generate_placements(self, birth_data: BirthData) -> PlacementsResponse:
        """
        Generate natal chart placements for profile display.

        Args:
            birth_data: Birth information

        Returns:
            PlacementsResponse with sun, moon, ascendant, and all 10 planets
        """
        # Calculate natal chart
        natal_chart = self.provider.calculate_natal_chart(birth_data)

        # Planet names in order (10 planets)
        planet_names = [
            "sun", "moon", "mercury", "venus", "mars",
            "jupiter", "saturn", "uranus", "neptune", "pluto"
        ]

        # Display names mapping
        display_names = {
            "sun": "Sun",
            "moon": "Moon",
            "mercury": "Mercury",
            "venus": "Venus",
            "mars": "Mars",
            "jupiter": "Jupiter",
            "saturn": "Saturn",
            "uranus": "Uranus",
            "neptune": "Neptune",
            "pluto": "Pluto",
        }

        # Extract all planet placements
        planets: list[PlacementItem] = []
        for planet_name in planet_names:
            planet_data = natal_chart.planets.get(planet_name)
            if planet_data:
                planets.append(PlacementItem(
                    name=display_names.get(planet_name, planet_name.title()),
                    sign=planet_data.get("sign", "Unknown"),
                    house=self._parse_house(planet_data.get("house"))
                ))

        # Extract sun placement
        sun_data = natal_chart.planets.get("sun", {})
        sun = PlacementItem(
            name="Sun",
            sign=sun_data.get("sign", "Unknown"),
            house=self._parse_house(sun_data.get("house"))
        )

        # Extract moon placement
        moon_data = natal_chart.planets.get("moon", {})
        moon = PlacementItem(
            name="Moon",
            sign=moon_data.get("sign", "Unknown"),
            house=self._parse_house(moon_data.get("house"))
        )

        # Extract ascendant placement (from points, no house)
        ascendant_data = natal_chart.points.get("ascendant", {})
        ascendant = PlacementItem(
            name="Ascendant",
            sign=ascendant_data.get("sign", "Unknown"),
            house=None  # Ascendant defines the 1st house cusp, not in a house
        )

        return PlacementsResponse(
            sun=sun,
            moon=moon,
            ascendant=ascendant,
            planets=planets,
            chart_system=natal_chart.chart_system,
        )
