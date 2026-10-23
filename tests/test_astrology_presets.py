"""Regression tests for astrology preset configuration."""

from app.config.astrology_presets import DetailLevel, get_preset
from app.config.chart_system import HouseSystem, Zodiac, chart_system_config
from app.domain.models import BirthData
from app.infrastructure.providers.kerykeion_provider import KerykeionProvider

DEFAULT_CHART_SYSTEM = chart_system_config(Zodiac.WESTERN, HouseSystem.PLACIDUS)


def test_core_preset_includes_nodes_and_chiron():
    """CORE profiles should request both node fields and Chiron."""
    config = get_preset(DetailLevel.CORE)

    assert "true_north_lunar_node" in config.points
    assert "true_south_lunar_node" in config.points
    assert "chiron" in config.planets


def test_core_provider_extracts_nodes_into_points_without_duplication():
    """CORE chart payloads should surface nodes in points without duplicating them."""
    provider = KerykeionProvider(
        config=get_preset(DetailLevel.CORE),
        chart_system=DEFAULT_CHART_SYSTEM,
    )

    chart = provider.calculate_natal_chart(
        BirthData(
            year=1990,
            month=3,
            day=15,
            hour=14,
            minute=30,
            latitude=40.7128,
            longitude=-74.0060,
            timezone="America/New_York",
        )
    )

    assert "true_north_lunar_node" in chart.points
    assert "true_south_lunar_node" in chart.points
    assert "chiron" in chart.planets
    assert "ascendant" not in chart.planets
    assert "medium_coeli" not in chart.planets
    assert "true_north_lunar_node" not in chart.planets
    assert "true_south_lunar_node" not in chart.planets
