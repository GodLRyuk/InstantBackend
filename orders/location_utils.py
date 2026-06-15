# orders/location_utils.py

from geopy.geocoders import Nominatim
from geopy.distance import geodesic

MAX_RADIUS_KM = 10  # max allowed distance in km

geolocator = Nominatim(user_agent="your_app_name")


def geocode_pincode(pincode: str) -> dict | None:
    """
    Geocode a pincode (India) and return lat, lng, and resolved pincode.
    Returns None if geocoding fails.
    """
    try:
        location = geolocator.geocode(f"{pincode}, India", addressdetails=True, timeout=5)
        if not location:
            return None

        raw = location.raw.get("address", {})
        resolved_pincode = raw.get("postcode", "").strip()

        return {
            "lat": location.latitude,
            "lng": location.longitude,
            "pincode": resolved_pincode,
        }
    except Exception:
        return None


def reverse_geocode(lat: float, lng: float) -> dict | None:
    """
    Reverse geocode lat/lng to get the pincode at that location.
    Returns None if it fails.
    """
    try:
        location = geolocator.reverse((lat, lng), exactly_one=True, addressdetails=True, timeout=5)
        if not location:
            return None

        raw = location.raw.get("address", {})
        pincode = raw.get("postcode", "").strip()

        return {
            "pincode": pincode,
        }
    except Exception:
        return None


def validate_user_location(current_lat: float, current_lng: float, address_pincode: str) -> dict:
    """
    Full validation:
    1. Reverse geocode user's current location → get current pincode
    2. Geocode address pincode → get address lat/lng
    3. Check pincode match
    4. Check distance within MAX_RADIUS_KM

    Returns:
        {
            "valid": bool,
            "error": str | None,       # human-readable reason if invalid
            "distance_km": float | None
        }
    """
    # Step 1: resolve user's current pincode from GPS
    current_location_info = reverse_geocode(current_lat, current_lng)
    if not current_location_info:
        return {"valid": False, "error": "Could not determine your current location. Please try again.", "distance_km": None}

    current_pincode = current_location_info["pincode"]

    # Step 2: geocode the delivery address pincode
    address_location_info = geocode_pincode(address_pincode)
    if not address_location_info:
        return {"valid": False, "error": "Could not verify the delivery address location. Please try again.", "distance_km": None}

    address_lat = address_location_info["lat"]
    address_lng = address_location_info["lng"]
    address_resolved_pincode = address_location_info["pincode"]

    # Step 3: pincode match check
    if current_pincode != address_resolved_pincode:
        return {
            "valid": False,
            "error": (
                f"Your current location (pincode: {current_pincode}) does not match "
                f"the selected delivery address (pincode: {address_resolved_pincode}). "
                f"Please select the correct address or move to the delivery location."
            ),
            "distance_km": None,
        }

    # Step 4: distance check
    distance_km = geodesic(
        (current_lat, current_lng),
        (address_lat, address_lng)
    ).km

    if distance_km > MAX_RADIUS_KM:
        return {
            "valid": False,
            "error": (
                f"You are {distance_km:.1f} km away from the delivery address. "
                f"Maximum allowed distance is {MAX_RADIUS_KM} km."
            ),
            "distance_km": round(distance_km, 2),
        }

    return {"valid": True, "error": None, "distance_km": round(distance_km, 2)}