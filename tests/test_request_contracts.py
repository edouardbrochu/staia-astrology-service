"""Astrology service request contract validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.requests import ProfileRequest, RelationshipRequest, TransitPeriodRequest


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            ProfileRequest,
            {"year": 1990, "month": 1, "day": 1, "unexpected": True},
        ),
        (
            TransitPeriodRequest,
            {
                "year": 1990,
                "month": 1,
                "day": 1,
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "unexpected": True,
            },
        ),
        (
            RelationshipRequest,
            {
                "person1": {"year": 1990, "month": 1, "day": 1},
                "person2": {"year": 1991, "month": 2, "day": 2},
                "unexpected": True,
            },
        ),
    ],
)
def test_astrology_request_models_reject_unknown_top_level_fields(model, payload) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)
