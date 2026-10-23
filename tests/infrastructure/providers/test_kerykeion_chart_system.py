"""Tests for the canonical chart-system configuration."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from app.config.astrology_presets import DetailLevel, get_preset
from app.config.chart_system import HouseSystem, Zodiac, chart_system_config
from app.domain.models import BirthData
from app.infrastructure.providers.kerykeion_chart_factory import KerykeionChartFactory
from app.infrastructure.providers.kerykeion_provider import KerykeionProvider

DEFAULT_CHART_SYSTEM = chart_system_config(Zodiac.WESTERN, HouseSystem.PLACIDUS)


def _birth_data() -> BirthData:
    return BirthData(
        year=1990,
        month=6,
        day=15,
        hour=14,
        minute=30,
        latitude=40.7128,
        longitude=-74.0060,
        timezone="America/New_York",
    )


def _provider() -> KerykeionProvider:
    return KerykeionProvider(
        config=get_preset(DetailLevel.CORE),
        chart_system=DEFAULT_CHART_SYSTEM,
    )


def test_natal_chart_uses_explicit_tropical_placidus_settings():
    provider = _provider()

    natal_chart = provider.calculate_natal_chart(_birth_data())
    subject = natal_chart.provider_data

    assert natal_chart.chart_system["id"] == "western_tropical_placidus"
    assert subject.zodiac_type == "Tropical"
    assert subject.houses_system_identifier == "P"
    assert subject.sidereal_mode is None
    assert subject.perspective_type == "Apparent Geocentric"


def test_placidus_house_cusps_are_not_snapped_to_sign_boundaries():
    provider = _provider()

    natal_chart = provider.calculate_natal_chart(_birth_data())
    first_house_abs_pos = natal_chart.houses["first_house"]["abs_pos"]
    second_house_abs_pos = natal_chart.houses["second_house"]["abs_pos"]

    assert natal_chart.houses["first_house"]["sign"] == natal_chart.points["ascendant"]["sign"]
    assert first_house_abs_pos == pytest.approx(193.6954, abs=0.01)
    assert second_house_abs_pos == pytest.approx(220.7712, abs=0.01)


def test_subject_factory_disables_dst_inference():
    factory = KerykeionChartFactory(chart_system=DEFAULT_CHART_SYSTEM)
    subject = Mock(
        zodiac_type=DEFAULT_CHART_SYSTEM.zodiac_type,
        houses_system_identifier=DEFAULT_CHART_SYSTEM.house_system_identifier,
        sidereal_mode=DEFAULT_CHART_SYSTEM.sidereal_mode,
        perspective_type=DEFAULT_CHART_SYSTEM.perspective_type,
    )

    with patch(
        "app.infrastructure.providers.kerykeion_chart_factory.AstrologicalSubjectFactory.from_birth_data",
        return_value=subject,
    ) as create_subject:
        assert factory.create_subject(name="Subject", birth_data=_birth_data()) is subject

    assert create_subject.call_args.kwargs["is_dst"] is False


def test_subject_factory_rejects_nonexistent_local_time_before_disabling_dst():
    factory = KerykeionChartFactory(chart_system=DEFAULT_CHART_SYSTEM)

    with (
        patch(
            "app.infrastructure.providers.kerykeion_chart_factory.AstrologicalSubjectFactory.from_birth_data"
        ) as create_subject,
        pytest.raises(ValueError, match="Nonexistent local time"),
    ):
        factory.create_subject(
            name="Subject",
            birth_data=BirthData(
                year=2024,
                month=3,
                day=10,
                hour=2,
                minute=30,
                latitude=40.7128,
                longitude=-74.0060,
                timezone="America/New_York",
            ),
        )

    create_subject.assert_not_called()


def test_subject_factory_uses_standard_time_for_ambiguous_local_time():
    factory = KerykeionChartFactory(chart_system=DEFAULT_CHART_SYSTEM)
    subject = Mock(
        zodiac_type=DEFAULT_CHART_SYSTEM.zodiac_type,
        houses_system_identifier=DEFAULT_CHART_SYSTEM.house_system_identifier,
        sidereal_mode=DEFAULT_CHART_SYSTEM.sidereal_mode,
        perspective_type=DEFAULT_CHART_SYSTEM.perspective_type,
    )

    with patch(
        "app.infrastructure.providers.kerykeion_chart_factory.AstrologicalSubjectFactory.from_birth_data",
        return_value=subject,
    ) as create_subject:
        factory.create_subject(
            name="Subject",
            birth_data=BirthData(
                year=2024,
                month=11,
                day=3,
                hour=1,
                minute=30,
                latitude=40.7128,
                longitude=-74.0060,
                timezone="America/New_York",
            ),
        )

    assert create_subject.call_args.kwargs["is_dst"] is False


def test_ephemeris_factory_disables_dst_inference():
    factory = KerykeionChartFactory(chart_system=DEFAULT_CHART_SYSTEM)

    with patch(
        "app.infrastructure.providers.kerykeion_chart_factory.EphemerisDataFactory",
        return_value=Mock(),
    ) as create_ephemeris:
        factory.create_ephemeris(
            start_datetime=datetime(2000, 1, 1),
            end_datetime=datetime(2000, 1, 3),
            location=_birth_data(),
            step_days=1,
            max_days=10,
        )

    assert create_ephemeris.call_args.kwargs["is_dst"] is False


def test_vedic_whole_sign_chart_is_sidereal_lahiri_with_nakshatras():
    provider = KerykeionProvider(
        config=get_preset(DetailLevel.CORE),
        chart_system=chart_system_config(Zodiac.VEDIC, HouseSystem.WHOLE_SIGN),
    )

    natal_chart = provider.calculate_natal_chart(_birth_data())
    subject = natal_chart.provider_data

    assert natal_chart.chart_system["id"] == "vedic_sidereal_lahiri_whole_sign"
    assert subject.zodiac_type == "Sidereal"
    assert subject.sidereal_mode == "LAHIRI"
    assert subject.houses_system_identifier == "W"
    # Tropical Sun is Gemini 24°; Lahiri moves it back about 24° into Gemini 0°.
    assert natal_chart.planets["sun"]["sign"] == "Gem"
    assert natal_chart.planets["sun"]["position"] == pytest.approx(0.2, abs=0.5)
    assert natal_chart.planets["sun"]["nakshatra"] == "Mrigashira 3"
    assert natal_chart.points["ascendant"]["nakshatra"]
    assert natal_chart.houses["first_house"]["position"] == 0
    assert natal_chart.houses["first_house"]["sign"] == natal_chart.points["ascendant"]["sign"]


@pytest.mark.parametrize(
    ("house_system", "chart_system_id", "identifier"),
    [
        (HouseSystem.WHOLE_SIGN, "western_tropical_whole_sign", "W"),
        (HouseSystem.EQUAL, "western_tropical_equal", "A"),
    ],
)
def test_western_house_system_choices(house_system, chart_system_id, identifier):
    provider = KerykeionProvider(
        config=get_preset(DetailLevel.CORE),
        chart_system=chart_system_config(Zodiac.WESTERN, house_system),
    )

    natal_chart = provider.calculate_natal_chart(_birth_data())

    assert natal_chart.chart_system["id"] == chart_system_id
    assert natal_chart.provider_data.houses_system_identifier == identifier
    assert natal_chart.planets["sun"]["sign"] == "Gem"
    assert "nakshatra" not in natal_chart.planets["sun"]
    ascendant = natal_chart.points["ascendant"]["abs_pos"]
    expected_first_cusp = ascendant if house_system == HouseSystem.EQUAL else ascendant - ascendant % 30
    assert natal_chart.houses["first_house"]["abs_pos"] == pytest.approx(expected_first_cusp, abs=0.01)
