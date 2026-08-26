import math
import requests
from geopy.distance import geodesic

# ── YOUR DARK STORE ────────────────────────────────────────
HUB_LAT = 23.263018678197362
HUB_LNG = 88.54218565679717
HUB_NAME = "Taherpur Instant Store"

MAX_RADIUS_KM = 10

# Google Maps API key — reuse the same key used for geocoding elsewhere.
GOOGLE_MAPS_API_KEY = "AIzaSyA_P5OTNZ0c7K9FLy2x6VMjiYl5SmcvNIc"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

# ✅ Fallback only — used when an address hasn't been geocoded yet
PINCODE_COORDS = {
    "741121": {"lat": 23.30489, "lng": 88.532026},
    "741122": {"lat": 23.989633, "lng": 88.688833},
    "741159": {"lat": 23.2619351, "lng": 88.5304314},
    "700091": {"lat": 22.5767672, "lng": 88.4300892},
}

ALLOWED_PINCODES = list(PINCODE_COORDS.keys())


def _road_distance_km(origin_lat, origin_lng, dest_lat, dest_lng):
    """
    Driving distance in km via Google Distance Matrix API.
    Returns None if the API call fails or returns no route —
    caller should fall back to straight-line distance in that case.
    """
    try:
        params = {
            "origins": f"{origin_lat},{origin_lng}",
            "destinations": f"{dest_lat},{dest_lng}",
            "mode": "driving",
            "key": GOOGLE_MAPS_API_KEY,
        }
        resp = requests.get(DISTANCE_MATRIX_URL, params=params, timeout=5)
        if resp.status_code != 200:
            return None

        data = resp.json()
        if data.get("status") != "OK":
            return None

        element = data["rows"][0]["elements"][0]
        if element.get("status") != "OK":
            return None

        meters = element["distance"]["value"]
        return round(meters / 1000, 2)
    except (requests.RequestException, KeyError, IndexError):
        return None


def validate_user_location(address) -> dict:
    """
    Checks if the delivery address is within MAX_RADIUS_KM of the dark store.
    Prefers the address's own geocoded lat/lng (precise). Falls back to the
    pincode centroid only if this address wasn't geocoded successfully.

    Distance shown to driver/customer is road distance (Distance Matrix API),
    not straight-line. Straight-line (geodesic) is used only as a cheap
    pre-filter — if it's already well beyond MAX_RADIUS_KM there's no point
    paying for a Distance Matrix call — and as a fallback if that API fails.
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

    straight_km = geodesic((HUB_LAT, HUB_LNG), (target_lat, target_lng)).km

    # Cheap pre-filter: road distance is always >= straight-line, so if
    # straight-line already blows past the radius by a wide margin, skip
    # the paid API call and reject immediately.
    if straight_km > MAX_RADIUS_KM * 1.5:
        return {
            "valid": False,
            "error": (
                f"Sorry, we don't deliver to this address yet. "
                f"We currently deliver within {MAX_RADIUS_KM} km of our store."
            ),
            "distance_km": round(straight_km, 2),
        }

    road_km = _road_distance_km(HUB_LAT, HUB_LNG, target_lat, target_lng)
    distance_km = road_km if road_km is not None else straight_km

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