import math
from decimal import Decimal, ROUND_HALF_UP


def haversine_km(lat1, lng1, lat2, lng2):
    """Straight-line distance in km between two lat/lng points."""
    r = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = p2 - p1
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def whole_rupees(value):
    """Round to a whole rupee, halves go up (same as the Flutter app)."""
    return Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def fmt_time(t):
    """time(23, 0) -> '11:00 pm'"""
    return t.strftime('%I:%M %p').lstrip('0').lower() if t else None
