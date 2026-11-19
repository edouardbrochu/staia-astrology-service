"""Tests for RelationshipService (compatibility service)."""

import pytest

from app.application.compatibility_service import RelationshipService
from app.config.astrology_presets import DetailLevel, get_preset
from app.config.chart_system import HouseSystem, Zodiac, chart_system_config
from app.domain.models import BirthData
from app.infrastructure.providers.kerykeion_provider import KerykeionProvider

DEFAULT_CHART_SYSTEM = chart_system_config(Zodiac.WESTERN, HouseSystem.PLACIDUS)


class TestRelationshipServiceRelationshipScore:
    """Tests for RelationshipService returning relationship_score in dict."""

    @pytest.fixture
    def service(self) -> RelationshipService:
        """Create a RelationshipService with KerykeionProvider."""
        provider = KerykeionProvider(
            config=get_preset(DetailLevel.CORE),
            chart_system=DEFAULT_CHART_SYSTEM,
        )
        return RelationshipService(provider=provider)

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

    def test_analyze_synastry_returns_relationship_score_dict(
        self, service: RelationshipService, person1_data: BirthData, person2_data: BirthData
    ):
        """analyze_synastry returns dict containing relationship_score."""
        result = service.analyze_synastry(person1_data, person2_data)

        assert "relationship_score" in result
        assert result["relationship_score"] is not None

    def test_relationship_score_dict_has_score_value(
        self, service: RelationshipService, person1_data: BirthData, person2_data: BirthData
    ):
        """relationship_score dict contains score_value."""
        result = service.analyze_synastry(person1_data, person2_data)

        assert "score_value" in result["relationship_score"]
        assert isinstance(result["relationship_score"]["score_value"], int)

    def test_relationship_score_dict_has_is_destiny_sign(
        self, service: RelationshipService, person1_data: BirthData, person2_data: BirthData
    ):
        """relationship_score dict contains is_destiny_sign."""
        result = service.analyze_synastry(person1_data, person2_data)

        assert "is_destiny_sign" in result["relationship_score"]
        assert isinstance(result["relationship_score"]["is_destiny_sign"], bool)

    def test_analyze_synastry_maintains_synastry_aspects(
        self, service: RelationshipService, person1_data: BirthData, person2_data: BirthData
    ):
        """analyze_synastry still returns synastry aspects."""
        result = service.analyze_synastry(person1_data, person2_data)

        assert "synastry" in result
        assert "aspects" in result["synastry"]
        assert isinstance(result["synastry"]["aspects"], list)

    def test_analyze_synastry_includes_chart_system_metadata(
        self, service: RelationshipService, person1_data: BirthData, person2_data: BirthData
    ):
        """Synastry responses include canonical chart-system metadata."""
        result = service.analyze_synastry(person1_data, person2_data)

        assert result["chart_system"]["id"] == "western_tropical_placidus"

    def test_analyze_synastry_compact_starts_with_chart_system_header(
        self, service: RelationshipService, person1_data: BirthData, person2_data: BirthData
    ):
        """Compact synastry output declares the chart system first."""
        result = service.analyze_synastry_compact(person1_data, person2_data)

        assert result.startswith("CHART_SYSTEM: western_tropical_placidus")


class TestRelationshipServiceComposite:
    """Tests for the midpoint composite chart."""

    @pytest.fixture
    def service(self) -> RelationshipService:
        provider = KerykeionProvider(
            config=get_preset(DetailLevel.CORE),
            chart_system=DEFAULT_CHART_SYSTEM,
        )
        return RelationshipService(provider=provider)

    @staticmethod
    def _noon_in_london(year: int, month: int, day: int) -> BirthData:
        return BirthData(
            year=year,
            month=month,
            day=day,
            hour=12,
            minute=0,
            latitude=51.5074,
            longitude=-0.1278,
            timezone="Europe/London",
        )

    @pytest.mark.parametrize(
        ("person1_date", "person2_date", "composite_sun"),
        [
            # Suns near 9° Aries and 9° Gemini: the midpoint is near 9° Taurus.
            ((1990, 3, 30), (1991, 5, 30), "Sun in Tau"),
            # Suns near 10° Pisces and 0° Taurus straddle 0° Aries: the midpoint
            # is near 5° Aries, not the opposite point in Libra.
            ((1990, 3, 1), (1991, 4, 20), "Sun in Ari"),
        ],
    )
    def test_composite_sun_is_the_midpoint_of_both_suns(
        self, service: RelationshipService, person1_date, person2_date, composite_sun
    ):
        text = service.analyze_composite_compact(
            self._noon_in_london(*person1_date),
            self._noon_in_london(*person2_date),
        )

        sun_line = next(line for line in text.splitlines() if line.startswith("Sun in "))
        assert sun_line.startswith(composite_sun)

    def test_composite_compact_is_a_full_chart(self, service: RelationshipService):
        text = service.analyze_composite_compact(
            self._noon_in_london(1990, 3, 30),
            self._noon_in_london(1991, 5, 30),
        )

        lines = text.splitlines()
        assert lines[0] == "CHART_SYSTEM: western_tropical_placidus"
        assert "NOTE:" not in text
        for heading in ("COMPOSITE CHART", "PLANETS", "POINTS", "HOUSES", "COMPOSITE ASPECTS"):
            assert heading in lines
