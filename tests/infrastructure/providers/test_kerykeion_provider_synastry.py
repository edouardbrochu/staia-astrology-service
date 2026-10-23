"""Tests for KerykeionProvider synastry score calculation."""

import pytest

from app.config.astrology_presets import DetailLevel, get_preset
from app.config.chart_system import HouseSystem, Zodiac, chart_system_config
from app.domain.models import BirthData
from app.infrastructure.providers.kerykeion_provider import KerykeionProvider

DEFAULT_CHART_SYSTEM = chart_system_config(Zodiac.WESTERN, HouseSystem.PLACIDUS)


class TestKerykeionProviderSynastryScore:
    """Tests for calculate_synastry returning relationship_score."""

    @pytest.fixture
    def provider(self) -> KerykeionProvider:
        """Create a KerykeionProvider instance."""
        return KerykeionProvider(
            config=get_preset(DetailLevel.CORE),
            chart_system=DEFAULT_CHART_SYSTEM,
        )

    @pytest.fixture
    def person1_data(self) -> BirthData:
        """Birth data for person 1."""
        return BirthData(
            year=1990,
            month=3,
            day=15,
            hour=14,
            minute=30,
            latitude=40.7128,
            longitude=-74.0060,
            timezone="America/New_York",
        )

    @pytest.fixture
    def person2_data(self) -> BirthData:
        """Birth data for person 2."""
        return BirthData(
            year=1992,
            month=7,
            day=22,
            hour=10,
            minute=15,
            latitude=34.0522,
            longitude=-118.2437,
            timezone="America/Los_Angeles",
        )

    def test_calculate_synastry_returns_relationship_score(
        self, provider: KerykeionProvider, person1_data: BirthData, person2_data: BirthData
    ):
        """calculate_synastry returns synastry with relationship_score."""
        chart1 = provider.calculate_natal_chart(person1_data)
        chart2 = provider.calculate_natal_chart(person2_data)

        synastry = provider.calculate_synastry(chart1, chart2)

        assert synastry.relationship_score is not None
        assert hasattr(synastry.relationship_score, "score_value")
        assert hasattr(synastry.relationship_score, "is_destiny_sign")

    def test_relationship_score_value_is_int(
        self, provider: KerykeionProvider, person1_data: BirthData, person2_data: BirthData
    ):
        """relationship_score.score_value is an integer."""
        chart1 = provider.calculate_natal_chart(person1_data)
        chart2 = provider.calculate_natal_chart(person2_data)

        synastry = provider.calculate_synastry(chart1, chart2)

        assert isinstance(synastry.relationship_score.score_value, int)

    def test_relationship_score_is_destiny_sign_is_bool(
        self, provider: KerykeionProvider, person1_data: BirthData, person2_data: BirthData
    ):
        """relationship_score.is_destiny_sign is a boolean."""
        chart1 = provider.calculate_natal_chart(person1_data)
        chart2 = provider.calculate_natal_chart(person2_data)

        synastry = provider.calculate_synastry(chart1, chart2)

        assert isinstance(synastry.relationship_score.is_destiny_sign, bool)

    def test_calculate_synastry_still_returns_aspects(
        self, provider: KerykeionProvider, person1_data: BirthData, person2_data: BirthData
    ):
        """calculate_synastry maintains aspects alongside relationship_score."""
        chart1 = provider.calculate_natal_chart(person1_data)
        chart2 = provider.calculate_natal_chart(person2_data)

        synastry = provider.calculate_synastry(chart1, chart2)

        # Should still have aspects
        assert hasattr(synastry, "aspects")
        assert isinstance(synastry.aspects, list)
        # Should have some aspects for different birth dates
        assert len(synastry.aspects) > 0
