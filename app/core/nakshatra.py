"""Nakshatra (lunar mansion) lookup for sidereal positions."""

NAKSHATRAS = (
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu",
    "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta",
    "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha",
    "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
    "Uttara Bhadrapada", "Revati",
)
PADAS_PER_NAKSHATRA = 4
PADA_COUNT = len(NAKSHATRAS) * PADAS_PER_NAKSHATRA


def nakshatra_label(sidereal_longitude: float) -> str:
    """Return the nakshatra and pada (1-4) for a sidereal longitude, e.g. "Swati 3"."""
    # Scale before dividing so exact boundaries (e.g. 120° = Magha 1) are not
    # pushed back by a rounded 13°20' span.
    pada_index = int(sidereal_longitude % 360 * PADA_COUNT // 360)
    index, pada = divmod(pada_index, PADAS_PER_NAKSHATRA)
    return f"{NAKSHATRAS[index]} {pada + 1}"
