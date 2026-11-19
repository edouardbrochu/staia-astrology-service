"""Relationship application service - orchestrates synastry and composite calculations."""

from app.application.unknown_birth_data_policy import (
    format_safe_partial_composite_chart,
    has_unknown_birth_data,
    prepend_note_after_chart_system,
    synastry_caution_note,
)
from app.core.llm_formatter import format_composite_chart, format_synastry
from app.domain.models import BirthData
from app.domain.ports import IAstrologyProvider


class RelationshipService:
    """
    Application service for two-person relationship astrology.

    Calculates synastry (cross-chart aspects) and the midpoint composite chart.
    """

    def __init__(self, provider: IAstrologyProvider):
        """
        Initialize with astrology provider.

        Args:
            provider: Astrology calculation provider (injected dependency)
        """
        self.provider = provider

    def analyze_synastry(self, person1_data: BirthData, person2_data: BirthData) -> dict:
        """
        Analyze synastry between two people.

        Args:
            person1_data: First person's birth information
            person2_data: Second person's birth information

        Returns:
            Dict containing synastry aspects and relationship score
        """
        # Calculate both natal charts
        chart1 = self.provider.calculate_natal_chart(person1_data)
        chart2 = self.provider.calculate_natal_chart(person2_data)

        # Calculate synastry
        synastry = self.provider.calculate_synastry(chart1, chart2)

        # Build relationship score dict if available
        relationship_score = None
        if synastry.relationship_score:
            relationship_score = {
                "score_value": synastry.relationship_score.score_value,
                "is_destiny_sign": synastry.relationship_score.is_destiny_sign,
            }

        # Return synastry data with relationship score
        return {
            "chart_system": chart1.chart_system,
            "synastry": {
                "aspects": synastry.aspects
            },
            "relationship_score": relationship_score,
        }

    def analyze_synastry_compact(
        self,
        person1_data: BirthData,
        person2_data: BirthData,
        *,
        person1_label: str | None = None,
        person2_label: str | None = None,
    ) -> str:
        """
        Analyze synastry with LLM-optimized compact output.

        Args:
            person1_data: First person's birth information
            person2_data: Second person's birth information

        Returns:
            Compact text format optimized for LLM consumption (~80% token reduction)
        """
        synastry_data = self.analyze_synastry(person1_data, person2_data)
        text = format_synastry(synastry_data)
        affected = _affected_people(person1_data, person1_label, person2_data, person2_label)
        if not affected:
            return text
        return prepend_note_after_chart_system(text, synastry_caution_note(affected))

    def analyze_composite_compact(
        self,
        person1_data: BirthData,
        person2_data: BirthData,
        *,
        person1_label: str | None = None,
        person2_label: str | None = None,
    ) -> str:
        """
        Calculate the midpoint composite chart with LLM-optimized compact output.

        With unknown birth time or location for either person, only planets
        whose composite sign is certain are returned, with a note.
        """
        affected = _affected_people(person1_data, person1_label, person2_data, person2_label)
        if affected:
            return format_safe_partial_composite_chart(
                provider=self.provider,
                person1_data=person1_data,
                person2_data=person2_data,
                affected=affected,
            )
        chart1 = self.provider.calculate_natal_chart(person1_data)
        chart2 = self.provider.calculate_natal_chart(person2_data)
        composite = self.provider.calculate_composite(chart1, chart2)
        return format_composite_chart(composite.model_dump())


def _affected_people(
    person1_data: BirthData,
    person1_label: str | None,
    person2_data: BirthData,
    person2_label: str | None,
) -> list[tuple[BirthData, str | None]]:
    """People whose birth time or location is unknown, with their labels."""
    return [
        (birth_data, label)
        for birth_data, label in ((person1_data, person1_label), (person2_data, person2_label))
        if has_unknown_birth_data(birth_data)
    ]
