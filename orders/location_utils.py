# orders/location_utils.py

from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# ── YOUR DARK STORE ────────────────────────────────────────
# Taherpur Station Rd, Taherpur, West Bengal 741159
HUB_LAT = 23.2593
HUB_LNG = 88.5429
HUB_NAME = "Taherpur Store"

# Blinkit-style: 10 km hard radius
MAX_RADIUS_KM = 10

ALLOWED_PINCODES = [
    "741121",  # Barasat Taherpur area
    "741122",
    "741159",  # Taherpur itself
    "700091",  # Salt Lake Sec 5
]

geolocator = Nominatim(user_agent="instant_delivery_app")


def geocode_pincode(pincode: str) -> dict | None:
    try:
        location = geolocator.geocode(
            f"{pincode}, West Bengal, India",
            addressdetails=True,
            timeout=5,
        )
        if not location:
            return None
        return {
            "lat": location.latitude,
            "lng": location.longitude,
        }
    except Exception:
        return None


def validate_user_location(
    current_lat: float, current_lng: float, address_pincode: str
) -> dict:
    """
    Blinkit-style: checks if the DELIVERY ADDRESS pincode
    is within MAX_RADIUS_KM of our dark store.
    User's current GPS is ignored entirely.
    """

    address_info = geocode_pincode(address_pincode)

    # Geocoding failed — fail open, pincode allowlist already filtered
    if not address_info:
        return {"valid": True, "error": None, "distance_km": None}

    distance_km = geodesic(
        (HUB_LAT, HUB_LNG),
        (address_info["lat"], address_info["lng"]),
    ).km

    if distance_km > MAX_RADIUS_KM:
        return {
            "valid": False,
            "error": (
                f"Sorry, we don't deliver to this address yet. "
                f"We currently deliver within {MAX_RADIUS_KM} km of our store."
            ),
            "distance_km": round(distance_km, 2),
        }

    return {
        "valid": True,
        "error": None,
        "distance_km": round(distance_km, 2),
    }