"""API request models using domain models for DRY compliance."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.birth_data import BirthData


class ProfileRequest(BirthData):
    """
    Request model for astrological profile (natal chart + transits).

    Inherits birth data fields from domain BirthData model.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "year": 1990,
                "month": 3,
                "day": 15,
                "hour": 14,
                "minute": 30,
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timezone": "America/New_York",
                "transit_date": "2025-10-30T12:00:00Z"
            }
        }
    )

    # Optional transit date (defaults to current time)
    transit_date: datetime | None = Field(
        None,
        description="Date/time for transit calculation (defaults to current time)"
    )
    subject_label: str | None = Field(
        None,
        description="LLM-facing subject label for precision notes",
    )


class TransitPeriodRequest(BirthData):
    """
    Request model for transit period calculation (past or future).

    Inherits birth data fields from domain BirthData model.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "year": 1990,
                "month": 3,
                "day": 15,
                "hour": 14,
                "minute": 30,
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timezone": "America/New_York",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31"
            }
        }
    )

    start_date: str = Field(
        ...,
        description="Start date for transit period in YYYY-MM-DD format",
        pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    end_date: str = Field(
        ...,
        description="End date for transit period in YYYY-MM-DD format",
        pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    subject_label: str | None = Field(
        None,
        description="LLM-facing subject label for precision notes",
    )


class SynastryRequest(BaseModel):
    """Request model for synastry analysis (relationship compatibility)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "person1": {
                    "year": 1990,
                    "month": 3,
                    "day": 15,
                    "hour": 14,
                    "minute": 30,
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "timezone": "America/New_York"
                },
                "person2": {
                    "year": 1992,
                    "month": 7,
                    "day": 22,
                    "hour": 8,
                    "minute": 15,
                    "latitude": 34.0522,
                    "longitude": -118.2437,
                    "timezone": "America/Los_Angeles"
                }
            }
        }
    )

    person1: BirthData = Field(..., description="Birth data for first person")
    person2: BirthData = Field(..., description="Birth data for second person")
    person1_label: str | None = Field(
        None,
        description="LLM-facing label for first person precision notes",
    )
    person2_label: str | None = Field(
        None,
        description="LLM-facing label for second person precision notes",
    )
