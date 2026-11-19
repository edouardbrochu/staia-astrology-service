"""Composite chart domain model."""

from typing import Any

from pydantic import BaseModel


class CompositeChart(BaseModel):
    """Midpoint composite chart: one chart for the relationship between two people."""

    chart_system: dict[str, Any]
    planets: dict[str, Any]
    houses: dict[str, Any]
    points: dict[str, Any]
    aspects: list[Any]
