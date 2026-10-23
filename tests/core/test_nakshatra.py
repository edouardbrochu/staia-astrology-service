"""Tests for nakshatra lookup."""

import pytest

from app.core.nakshatra import nakshatra_label


@pytest.mark.parametrize(
    ("longitude", "label"),
    [
        (0.0, "Ashwini 1"),
        (3.34, "Ashwini 2"),
        (13.34, "Bharani 1"),
        (120.0, "Magha 1"),
        (240.0, "Mula 1"),
        (40.0, "Rohini 1"),
        (194.0, "Swati 3"),
        (359.99, "Revati 4"),
        (360.0, "Ashwini 1"),
    ],
)
def test_nakshatra_label(longitude, label):
    assert nakshatra_label(longitude) == label
