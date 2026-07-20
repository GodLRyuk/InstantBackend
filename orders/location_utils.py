import math
from geopy.distance import geodesic

# ── YOUR DARK STORE ────────────────────────────────────────
HUB_LAT = 23.263018678197362
HUB_LNG = 88.54218565679717
HUB_NAME = "Taherpur Instant Store"

MAX_RADIUS_KM = 10

# ✅ Fallback only — used when an address hasn't been geocoded yet
PINCODE_COORDS = {
    "741121": {"lat": 23.30489, "lng": 88.532026},
    "741122": {"lat": 23.989633, "lng": 88.688833},
    "741159": {"lat": 23.2619351, "lng": 88.5304314},
    "700091": {"lat": 22.5767672, "lng": 88.4300892},
}

ALLOWED_PINCODES = list(PINCODE_COORDS.keys())


def validate_user_location(address) -> dict:
    """
    Checks if the delivery address is within MAX_RADIUS_KM of the dark store.
    Prefers the address's own geocoded lat/lng (precise). Falls back to the
    pincode centroid only if this address wasn't geocoded successfully.
    """
    if address.lat is not None and address.lng is not None:
        target_lat, target_lng = float(address.lat), float(address.lng)
    else:
        pincode = str(address.pincode).strip()
        coords = PINCODE_COORDS.get(pincode)
        if not coords:
            return {
                "valid": False,
                "error": "Sorry, we don't deliver to this pincode yet.",
                "distance_km": None,
            }
        target_lat, target_lng = coords["lat"], coords["lng"]

    distance_km = geodesic(
        (HUB_LAT, HUB_LNG),
        (target_lat, target_lng),
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


def calculate_delivery_fee(distance_km, base_fee=25, base_km=3, per_km_charge=5):
    """
    ₹25 flat for the first `base_km` (default 3km).
    Beyond that, +₹5 per additional km, rounding up partial km.
    """
    base_fee = float(base_fee)
    base_km = float(base_km)
    per_km_charge = float(per_km_charge)

    if distance_km is None or distance_km <= base_km:
        return base_fee

    extra_km = math.ceil(distance_km - base_km)
    return base_fee + (extra_km * per_km_charge)