"""Transit period application service - calculates transits over a date range."""

from datetime import date

from app.application.chart_payloads import llm_natal_chart_payload
from app.application.unknown_birth_data_policy import (
    has_unknown_birth_data,
    prepend_note_after_chart_system,
    transit_caution_note,
)
from app.core.llm_formatter import format_transit_periods
from app.domain.models import BirthData
from app.domain.ports import IAstrologyProvider


class TransitPeriodService:
    """
    Application service for generating transit data over a date range.

    Uses Kerykeion's TransitsTimeRangeFactory for precise timing of transit periods.
    """

    def __init__(self, provider: IAstrologyProvider):
        """
        Initialize with astrology provider.

        Args:
            provider: Astrology calculation provider (injected dependency)
        """
        self.provider = provider

    def generate_transit_period(
        self,
        birth_data: BirthData,
        start_date: str,
        end_date: str
    ) -> dict:
        """
        Generate transit data for a date range with precise timing.

        Args:
            birth_data: Birth information
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict containing period metadata, natal chart, and transit aspects with timing
        """
        # Parse dates
        start_dt = date.fromisoformat(start_date)
        end_dt = date.fromisoformat(end_date)

        # Validate date range
        if start_dt > end_dt:
            raise ValueError("start_date must be before or equal to end_date")

        days_diff = (end_dt - start_dt).days

        # Calculate natal chart
        natal_chart = self.provider.calculate_natal_chart(birth_data)

        # Calculate transit periods with precise timing
        transit_result = self.provider.calculate_transit_periods(
            natal_chart=natal_chart,
            start_date=start_dt,
            end_date=end_dt
        )

        # Convert TransitAspect objects to dicts for formatting
        aspects_data = [
            {
                "transit_planet": asp.transit_planet,
                "natal_planet": asp.natal_planet,
                "aspect_type": asp.aspect_type,
                "start_date": asp.start_date.isoformat(),
                "end_date": asp.end_date.isoformat(),
                "exact_date": asp.exact_date.isoformat(),
                "exact_orb": asp.exact_orb,
                "duration_days": (asp.end_date - asp.start_date).days + 1
            }
            for asp in transit_result.aspects
        ]

        return {
            "chart_system": natal_chart.chart_system,
            "period": {
                "start": start_date,
                "end": end_date,
                "days": days_diff
            },
            "natal_chart": llm_natal_chart_payload(natal_chart),
            "transit_aspects": aspects_data,
            "aspect_count": len(aspects_data)
        }

    def generate_transit_period_compact(
        self,
        birth_data: BirthData,
        start_date: str,
        end_date: str,
        *,
        subject_label: str | None = None,
    ) -> str:
        """
        Generate LLM-optimized compact transit period data.

        Args:
            birth_data: Birth information
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Compact text format optimized for LLM consumption
        """
        transit_data = self.generate_transit_period(birth_data, start_date, end_date)
        text = format_transit_periods(transit_data)
        if has_unknown_birth_data(birth_data):
            return prepend_note_after_chart_system(text, transit_caution_note(birth_data, subject_label))
        return text
