"""Kerykeion astrology provider implementation."""

from collections import defaultdict
from datetime import UTC, date, datetime

from kerykeion import (
    AspectsFactory,
    RelationshipScoreFactory,
    TransitsTimeRangeFactory,
)

from app.config.astrology_presets import AstrologyConfig
from app.config.chart_system import ChartSystemConfig
from app.core.exceptions import ChartCalculationException, InvalidBirthDataException
from app.core.extractors import extract_celestial_objects, filter_aspects_by_orb, filter_personal_synastry_aspects
from app.core.nakshatra import nakshatra_label
from app.core.temporal import normalize_transit_for_chart_timezone
from app.domain.models import (
    BirthData,
    NatalChart,
    RelationshipScore,
    Synastry,
    Transit,
    TransitAspect,
    TransitPeriodResult,
)
from app.domain.ports import IAstrologyProvider
from app.infrastructure.providers.kerykeion_chart_factory import KerykeionChartFactory

# Planets to track for transit periods (skip Moon - too fast, creates noise)
TRANSIT_PLANETS = ['Sun', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto']

# Outer planets (generational - transits between these are not personal)
OUTER_PLANETS = {'Uranus', 'Neptune', 'Pluto'}

# Aspects to track with their orbs
TRANSIT_ASPECTS = [
    {'name': 'conjunction', 'orb': 8},
    {'name': 'opposition', 'orb': 8},
    {'name': 'square', 'orb': 6},
    {'name': 'trine', 'orb': 6},
    {'name': 'sextile', 'orb': 4},
]

# Filtering thresholds
MAX_EXACT_ORB = 3.0  # Only include aspects that get within 3° of exact
MAX_DURATION_RATIO = 0.8  # Skip aspects active >80% of the period (background noise)
TARGET_CHAR_LIMIT = 3000  # Target output size
CHARS_PER_ASPECT = 50  # Average chars per aspect line
MAX_ASPECTS = TARGET_CHAR_LIMIT // CHARS_PER_ASPECT  # ~60 aspects

# Relevance weights for scoring
TRANSIT_PLANET_WEIGHT = {
    'Pluto': 10, 'Neptune': 9, 'Uranus': 8, 'Saturn': 7, 'Jupiter': 6,
    'Mars': 4, 'Sun': 2, 'Venus': 2, 'Mercury': 1
}
NATAL_PLANET_WEIGHT = {
    'Sun': 10, 'Moon': 10, 'Ascendant': 10, 'Medium_Coeli': 8,
    'Mars': 7, 'Venus': 7, 'Mercury': 5,
    'Jupiter': 4, 'Saturn': 4,
    'Uranus': 2, 'Neptune': 2, 'Pluto': 2, 'Chiron': 1
}
ASPECT_WEIGHT = {
    'conjunction': 10, 'opposition': 9, 'square': 8, 'trine': 5, 'sextile': 4
}


class KerykeionProvider(IAstrologyProvider):
    """
    Kerykeion-based implementation of the astrology provider port.

    This adapter isolates all Kerykeion-specific code, allowing easy
    substitution with other astrology libraries (Swiss Ephemeris, AstroAPI, etc.)
    """

    def __init__(self, config: AstrologyConfig, chart_system: ChartSystemConfig):
        """
        Initialize the Kerykeion provider with configuration.

        Args:
            config: Astrology configuration (planets, houses, orbs, etc.)
        """
        self.config = config
        self.chart_factory = KerykeionChartFactory(chart_system=chart_system)

    def _bodies(self, subject, names: list[str]) -> dict:
        """Extract planets or points, tagging each with its nakshatra in sidereal charts."""
        bodies = extract_celestial_objects(subject, names)
        if self.chart_factory.chart_system.zodiac_type == "Sidereal":
            for body in bodies.values():
                body["nakshatra"] = nakshatra_label(body["abs_pos"])
        return bodies

    def calculate_natal_chart(self, birth_data: BirthData) -> NatalChart:
        """
        Calculate a natal chart using Kerykeion.

        Args:
            birth_data: Birth information

        Returns:
            NatalChart domain model

        Raises:
            InvalidBirthDataException: If birth data is invalid
            ChartCalculationException: If calculation fails
        """
        try:
            # Create Kerykeion astrological subject
            subject = self.chart_factory.create_subject(name="Subject", birth_data=birth_data)

            # Calculate aspects
            aspects_result = AspectsFactory.single_chart_aspects(subject)

            # Extract data using DRY utilities
            planets = self._bodies(subject, self.config.planets)
            points = self._bodies(subject, self.config.points)
            houses = extract_celestial_objects(subject, self.config.houses)
            aspects = filter_aspects_by_orb(aspects_result, self.config.natal_orb)

            # Add birth metadata
            birth_metadata = {
                "name": subject.name,
                "date": subject.iso_formatted_local_datetime,
                "location": {
                    "city": subject.city if hasattr(subject, 'city') else None,
                    "nation": subject.nation if hasattr(subject, 'nation') else None,
                    "lat": subject.lat,
                    "lng": subject.lng,
                    "timezone": subject.tz_str
                },
                "lunar_phase": subject.lunar_phase.model_dump() if hasattr(subject, 'lunar_phase') else None
            }

            # Build domain model
            natal_chart = NatalChart(
                birth_data=birth_data,
                chart_system=self.chart_factory.metadata(),
                planets={**planets, "birth_data": birth_metadata},
                houses=houses,
                points=points,
                aspects=aspects,
                provider_data=subject  # Keep Kerykeion subject for synastry
            )

            return natal_chart

        except ValueError as e:
            raise InvalidBirthDataException(f"Invalid birth data: {str(e)}")
        except Exception as e:
            raise ChartCalculationException(f"Failed to calculate chart: {str(e)}")

    def calculate_synastry(self, chart1: NatalChart, chart2: NatalChart) -> Synastry:
        """
        Calculate synastry aspects using Kerykeion.

        Args:
            chart1: First person's natal chart
            chart2: Second person's natal chart

        Returns:
            Synastry domain model

        Raises:
            ChartCalculationException: If synastry calculation fails
        """
        try:
            # Extract Kerykeion subjects from provider data
            subject1 = chart1.provider_data
            subject2 = chart2.provider_data

            if not subject1 or not subject2:
                raise ChartCalculationException("Charts missing provider data for synastry calculation")

            # Calculate dual chart aspects
            aspects_result = AspectsFactory.dual_chart_aspects(subject1, subject2)

            # Filter aspects by orb
            aspects = filter_aspects_by_orb(aspects_result, self.config.synastry_orb)

            # Filter to personally relevant aspects (remove generational outer-to-outer)
            aspects = filter_personal_synastry_aspects(aspects)

            # Calculate relationship score using Ciro Discepolo's method
            score_factory = RelationshipScoreFactory(
                subject1, subject2, use_only_major_aspects=True
            )
            score_result = score_factory.get_relationship_score()
            relationship_score = RelationshipScore(
                score_value=score_result.score_value,
                is_destiny_sign=score_result.is_destiny_sign,
            )

            # Build domain model
            synastry = Synastry(
                chart1=chart1,
                chart2=chart2,
                aspects=aspects,
                relationship_score=relationship_score,
            )

            return synastry

        except Exception as e:
            raise ChartCalculationException(f"Failed to calculate synastry: {str(e)}")

    def calculate_transits(
        self,
        natal_chart: NatalChart,
        transit_date: datetime,
    ) -> Transit:
        """
        Calculate transits using Kerykeion.

        Args:
            natal_chart: The natal chart to calculate transits for
            transit_date: Date/time for transit calculation

        Returns:
            Transit domain model

        Raises:
            ChartCalculationException: If transit calculation fails
        """
        try:
            # Create transit subject for the given date
            birth_data = natal_chart.birth_data
            transit_local = normalize_transit_for_chart_timezone(
                transit_date=transit_date,
                chart_timezone=birth_data.timezone,
            )
            transit_subject = self.chart_factory.create_subject(
                name="Transit",
                birth_data=BirthData(
                    year=transit_local.year,
                    month=transit_local.month,
                    day=transit_local.day,
                    hour=transit_local.hour,
                    minute=transit_local.minute,
                    latitude=birth_data.latitude,
                    longitude=birth_data.longitude,
                    timezone=birth_data.timezone,
                ),
            )

            # Extract transit planets
            transit_planets = self._bodies(transit_subject, self.config.planets)
            transit_points = self._bodies(transit_subject, self.config.points)

            # Calculate transit-to-natal aspects
            natal_subject = natal_chart.provider_data
            if natal_subject:
                aspects_result = AspectsFactory.dual_chart_aspects(transit_subject, natal_subject)
                transit_to_natal_aspects = filter_aspects_by_orb(aspects_result, self.config.transit_orb)
            else:
                transit_to_natal_aspects = []

            # Calculate current sky aspects (transiting planets to each other)
            sky_aspects_result = AspectsFactory.single_chart_aspects(transit_subject)
            current_sky_aspects = filter_aspects_by_orb(sky_aspects_result, self.config.transit_orb)

            # Build domain model
            transit = Transit(
                date=transit_local,
                planets=transit_planets,
                points=transit_points,
                aspects_to_natal=transit_to_natal_aspects,
                current_sky_aspects=current_sky_aspects
            )

            return transit

        except Exception as e:
            raise ChartCalculationException(f"Failed to calculate transits: {str(e)}")

    def calculate_transit_periods(
        self,
        natal_chart: NatalChart,
        start_date: date,
        end_date: date,
    ) -> TransitPeriodResult:
        """
        Calculate transit periods with precise timing using Kerykeion's TransitsTimeRangeFactory.

        Args:
            natal_chart: The natal chart to calculate transits for
            start_date: Start date of the period
            end_date: End date of the period

        Returns:
            TransitPeriodResult with list of TransitAspects

        Raises:
            ChartCalculationException: If calculation fails
        """
        try:
            birth_data = natal_chart.birth_data
            natal_subject = natal_chart.provider_data

            if not natal_subject:
                raise ChartCalculationException("Natal chart missing provider data")

            # Convert dates to datetime for Kerykeion
            start_dt = datetime(start_date.year, start_date.month, start_date.day, 12, 0, tzinfo=UTC)
            end_dt = datetime(end_date.year, end_date.month, end_date.day, 12, 0, tzinfo=UTC)

            # Determine step size based on period length
            # Daily for short periods, weekly/monthly for longer
            total_days = (end_date - start_date).days
            if total_days <= 365:
                step_days = 1  # Daily for up to 1 year
            elif total_days <= 365 * 5:
                step_days = 7  # Weekly for 1-5 years
            else:
                step_days = 30  # Monthly for 5+ years

            # Generate ephemeris data
            ephemeris = self.chart_factory.create_ephemeris(
                start_datetime=start_dt,
                end_datetime=end_dt,
                location=birth_data,
                step_days=step_days,
                max_days=15000,
            )

            ephemeris_points = ephemeris.get_ephemeris_data_as_astrological_subjects()

            # Use TransitsTimeRangeFactory to get all aspects
            transits_factory = TransitsTimeRangeFactory(
                natal_chart=natal_subject,
                ephemeris_data_points=ephemeris_points,
                active_points=TRANSIT_PLANETS,
                active_aspects=TRANSIT_ASPECTS,
            )

            result = transits_factory.get_transit_moments()

            # Post-process to extract periods with exact dates
            aspects = self._extract_transit_periods(result.transits, start_date, end_date)

            return TransitPeriodResult(
                start_date=start_date,
                end_date=end_date,
                aspects=aspects
            )

        except Exception as e:
            raise ChartCalculationException(f"Failed to calculate transit periods: {str(e)}")

    def _extract_transit_periods(
        self,
        transits: list,
        start_date: date,
        end_date: date
    ) -> list[TransitAspect]:
        """
        Extract transit periods from raw Kerykeion transit data.

        Groups daily aspect data into continuous periods and finds exact dates.
        Applies relevance scoring to limit output to ~3K chars regardless of period length.
        """
        total_days = (end_date - start_date).days + 1

        # Track aspects across time: key -> list of (date, orb) tuples
        aspect_timeline: dict[str, list[tuple[date, float]]] = defaultdict(list)

        for transit in transits:
            # Parse date from ISO format
            transit_date_str = transit.date[:10]
            transit_date = date.fromisoformat(transit_date_str)

            for asp in transit.aspects:
                transit_planet = asp.p1_name
                natal_planet = asp.p2_name

                # Skip outer-to-outer transits (generational, not personal)
                if transit_planet in OUTER_PLANETS and natal_planet in OUTER_PLANETS:
                    continue

                key = f"{transit_planet}|{asp.aspect}|{natal_planet}"
                aspect_timeline[key].append((transit_date, abs(asp.orbit)))

        # Convert timeline to TransitAspect objects with scoring
        scored_aspects: list[tuple[float, TransitAspect]] = []

        for key, timeline in aspect_timeline.items():
            if len(timeline) < 1:
                continue

            parts = key.split('|')
            transit_planet = parts[0]
            aspect_type = parts[1]
            natal_planet = parts[2]

            timeline.sort(key=lambda x: x[0])

            # Find exact date (minimum orb)
            min_orb_entry = min(timeline, key=lambda x: x[1])
            exact_date = min_orb_entry[0]
            exact_orb = min_orb_entry[1]

            # Filter: skip if never gets close to exact
            if exact_orb > MAX_EXACT_ORB:
                continue

            period_start = timeline[0][0]
            period_end = timeline[-1][0]
            duration_days = (period_end - period_start).days + 1

            # Filter: skip if active for too much of the period (background noise)
            duration_ratio = duration_days / total_days
            if duration_ratio > MAX_DURATION_RATIO:
                continue

            # Calculate relevance score
            score = self._calculate_relevance_score(
                transit_planet, natal_planet, aspect_type, exact_orb
            )

            aspect = TransitAspect(
                transit_planet=transit_planet,
                natal_planet=natal_planet,
                aspect_type=aspect_type,
                start_date=period_start,
                end_date=period_end,
                exact_date=exact_date,
                exact_orb=round(exact_orb, 2)
            )
            scored_aspects.append((score, aspect))

        # Sort by score (highest first), then take top N
        scored_aspects.sort(key=lambda x: x[0], reverse=True)
        top_aspects = [asp for _, asp in scored_aspects[:MAX_ASPECTS]]

        # Re-sort by exact date for chronological output
        top_aspects.sort(key=lambda x: x.exact_date)

        return top_aspects

    @staticmethod
    def _calculate_relevance_score(
        transit_planet: str,
        natal_planet: str,
        aspect_type: str,
        exact_orb: float
    ) -> float:
        """
        Calculate relevance score for an aspect.

        Higher score = more astrologically significant.
        Score = transit_weight × natal_weight × aspect_weight × orb_weight
        """
        transit_w = TRANSIT_PLANET_WEIGHT.get(transit_planet, 1)
        natal_w = NATAL_PLANET_WEIGHT.get(natal_planet, 1)
        aspect_w = ASPECT_WEIGHT.get(aspect_type.lower(), 1)

        # Orb weight: tighter orb = higher score (0° = 10, 3° = 1)
        orb_w = max(1, 10 - (exact_orb * 3))

        return transit_w * natal_w * aspect_w * orb_w
