from datetime import date

from app.application.compatibility_service import SynastryService
from app.application.profile_service import ProfileService
from app.application.transit_period_service import TransitPeriodService
from app.domain.models import BirthData, NatalChart, RelationshipScore, Synastry, Transit, TransitPeriodResult


class FakeProvider:
    def __init__(self):
        self.chart_calls: list[BirthData] = []

    def calculate_natal_chart(self, birth_data: BirthData) -> NatalChart:
        self.chart_calls.append(birth_data)
        moon_sign = "Cancer" if len(self.chart_calls) % 2 else "Leo"
        return NatalChart(
            birth_data=birth_data,
            chart_system={"id": "western_tropical_placidus"},
            planets={
                "sun": {"name": "Sun", "sign": "Aries", "position": 1, "house": "first_house"},
                "moon": {"name": "Moon", "sign": moon_sign, "position": 2, "house": "second_house"},
            },
            houses={"first_house": {"name": "First House", "sign": "Aries"}},
            points={"ascendant": {"name": "Ascendant", "sign": "Libra", "position": 3}},
            aspects=[
                {"p1_name": "Sun", "p2_name": "Moon", "aspect": "conjunction", "orbit": 1.0},
            ],
        )

    def calculate_transits(self, natal_chart, transit_date):
        return Transit(
            date=transit_date,
            planets={},
            points={},
            aspects_to_natal=[],
            current_sky_aspects=[],
        )

    def calculate_synastry(self, chart1: NatalChart, chart2: NatalChart) -> Synastry:
        return Synastry(
            chart1=chart1,
            chart2=chart2,
            aspects=[
                {"p1_name": "Sun", "p2_name": "Moon", "aspect": "trine", "orbit": 2.0},
            ],
            relationship_score=RelationshipScore(score_value=10, is_destiny_sign=False),
        )

    def calculate_transit_periods(self, natal_chart: NatalChart, start_date: date, end_date: date):
        return TransitPeriodResult(start_date=start_date, end_date=end_date, aspects=[])


def test_safe_unknown_birth_data_filters_natal_chart_to_stable_signs_and_note():
    provider = FakeProvider()
    service = ProfileService(provider=provider)

    text = service.generate_personal_profile_compact(
        BirthData(
            year=1990,
            month=1,
            day=1,
            birth_time_known=False,
            birth_location_known=True,
            timezone="Europe/London",
        ),
        subject_label="the user",
    )

    assert text.splitlines() == [
        "CHART_SYSTEM: western_tropical_placidus",
        "NOTE: birth time for the user is unknown; ascendant, houses, house placements, points, exact degrees, aspects, transit aspects, and exact orbs were omitted.",
        "",
        "PLANETS",
        "Sun in Aries",
    ]


def test_safe_unknown_birth_data_unknown_location_preserves_midnight_birth_time():
    provider = FakeProvider()
    service = ProfileService(provider=provider)

    service.generate_personal_profile_compact(
        BirthData(
            year=1990,
            month=1,
            day=1,
            hour=0,
            minute=15,
            birth_time_known=True,
            birth_location_known=False,
        ),
        subject_label="the user",
    )

    start_boundary = provider.chart_calls[0]
    end_boundary = provider.chart_calls[1]
    assert (
        start_boundary.year,
        start_boundary.month,
        start_boundary.day,
        start_boundary.hour,
        start_boundary.minute,
    ) == (1989, 12, 31, 10, 15)
    assert (
        end_boundary.year,
        end_boundary.month,
        end_boundary.day,
        end_boundary.hour,
        end_boundary.minute,
    ) == (1990, 1, 1, 12, 15)


def test_safe_unknown_birth_data_adds_synastry_caution_without_filtering_content():
    service = SynastryService(provider=FakeProvider())

    text = service.analyze_synastry_compact(
        BirthData(year=1990, month=1, day=1, birth_time_known=False),
        BirthData(year=1991, month=1, day=1, birth_location_known=False),
        person1_label="the user",
        person2_label="Maya",
    )

    assert text.startswith(
        "CHART_SYSTEM: western_tropical_placidus\n"
        "NOTE: birth time for the user is unknown; birth location for Maya is unknown; "
        "some time-sensitive synastry may be less precise."
    )
    assert "COMPATIBILITY:" in text
    assert "SYNASTRY ASPECTS" in text


def test_safe_unknown_birth_data_adds_transit_caution_without_filtering_content():
    service = TransitPeriodService(provider=FakeProvider())

    text = service.generate_transit_period_compact(
        BirthData(year=1990, month=1, day=1, birth_time_known=False),
        "2026-01-01",
        "2026-01-07",
        subject_label="the user",
    )

    assert text.splitlines() == [
        "CHART_SYSTEM: western_tropical_placidus",
        "NOTE: birth time for the user is unknown; exact transit timing may be less precise.",
        "",
        "TRANSITS 2026-01-01 to 2026-01-07",
    ]
