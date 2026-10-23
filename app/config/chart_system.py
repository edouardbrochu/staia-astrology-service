"""Chart-system configuration for the astrology service."""

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal


class Zodiac(StrEnum):
    """User-selectable zodiac."""

    WESTERN = "western"
    VEDIC = "vedic"


class HouseSystem(StrEnum):
    """User-selectable house system."""

    PLACIDUS = "placidus"
    WHOLE_SIGN = "whole_sign"
    EQUAL = "equal"


ZODIAC_PREFIXES = {
    Zodiac.WESTERN: "western_tropical",
    Zodiac.VEDIC: "vedic_sidereal_lahiri",
}

HOUSE_SYSTEMS = {
    HouseSystem.PLACIDUS: ("Placidus", "P"),
    HouseSystem.WHOLE_SIGN: ("Whole Sign", "W"),
    HouseSystem.EQUAL: ("Equal", "A"),
}


@dataclass(frozen=True)
class ChartSystemConfig:
    """Settings applied to every calculation in one request."""

    id: str
    zodiac_type: Literal["Tropical", "Sidereal"]
    house_system: str
    house_system_identifier: str
    perspective_type: Literal[
        "Apparent Geocentric",
        "Heliocentric",
        "Topocentric",
        "True Geocentric",
    ]
    provider: str
    sidereal_mode: str | None = None

    def to_metadata(self) -> dict[str, str | None]:
        """Serialize chart-system settings for API responses."""
        return asdict(self)


def chart_system_config(zodiac: Zodiac, house_system: HouseSystem) -> ChartSystemConfig:
    """Build the calculation settings for a user's zodiac and house system."""
    house_label, house_identifier = HOUSE_SYSTEMS[house_system]
    is_vedic = zodiac == Zodiac.VEDIC
    return ChartSystemConfig(
        id=f"{ZODIAC_PREFIXES[zodiac]}_{house_system.value}",
        zodiac_type="Sidereal" if is_vedic else "Tropical",
        house_system=house_label,
        house_system_identifier=house_identifier,
        perspective_type="Apparent Geocentric",
        provider="kerykeion",
        sidereal_mode="LAHIRI" if is_vedic else None,
    )
