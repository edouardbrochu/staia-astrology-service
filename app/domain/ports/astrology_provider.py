"""Astrology provider port (interface) for hexagonal architecture."""

from abc import ABC, abstractmethod
from datetime import date, datetime

from app.domain.models import BirthData, CompositeChart, NatalChart, Synastry, Transit, TransitPeriodResult


class IAstrologyProvider(ABC):
    """
    Port (interface) for astrology calculation providers.

    This abstraction allows swapping between different astrology libraries
    (Kerykeion, Swiss Ephemeris, AstroAPI, etc.) without changing business logic.

    Implementations must convert provider-specific data structures to domain models.
    """

    @abstractmethod
    def calculate_natal_chart(self, birth_data: BirthData) -> NatalChart:
        """
        Calculate a natal chart for given birth data.

        Args:
            birth_data: Birth information

        Returns:
            NatalChart domain model with planets, houses, points, and aspects

        Raises:
            InvalidBirthDataException: If birth data is invalid
            ChartCalculationException: If calculation fails
        """
        pass

    @abstractmethod
    def calculate_synastry(self, chart1: NatalChart, chart2: NatalChart) -> Synastry:
        """
        Calculate synastry aspects between two natal charts.

        Args:
            chart1: First person's natal chart
            chart2: Second person's natal chart

        Returns:
            Synastry domain model with relationship aspects

        Raises:
            ChartCalculationException: If synastry calculation fails
        """
        pass

    @abstractmethod
    def calculate_composite(self, chart1: NatalChart, chart2: NatalChart) -> CompositeChart:
        """
        Calculate the midpoint composite chart of two natal charts.

        Args:
            chart1: First person's natal chart
            chart2: Second person's natal chart

        Returns:
            CompositeChart domain model with planets, points, houses, and aspects

        Raises:
            ChartCalculationException: If composite calculation fails
        """
        pass

    @abstractmethod
    def calculate_transits(
        self,
        natal_chart: NatalChart,
        transit_date: datetime,
    ) -> Transit:
        """
        Calculate current transits for a natal chart.

        Args:
            natal_chart: The natal chart to calculate transits for
            transit_date: Date/time for transit calculation

        Returns:
            Transit domain model with current planetary positions and aspects

        Raises:
            ChartCalculationException: If transit calculation fails
        """
        pass

    @abstractmethod
    def calculate_transit_periods(
        self,
        natal_chart: NatalChart,
        start_date: date,
        end_date: date,
    ) -> TransitPeriodResult:
        """
        Calculate transit periods with precise timing for a date range.

        Uses daily ephemeris to find when aspects become exact and their active periods.

        Args:
            natal_chart: The natal chart to calculate transits for
            start_date: Start date of the period
            end_date: End date of the period

        Returns:
            TransitPeriodResult with list of TransitAspects containing:
            - Active period (start_date to end_date within orb)
            - Exact date (when aspect is closest)
            - Exact orb (minimum orb achieved)

        Raises:
            ChartCalculationException: If calculation fails
        """
        pass
