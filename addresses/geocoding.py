from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="instant_delivery_app")


def geocode_address(full_address, city, state, pincode):
    """
    Tries pincode-based queries first, since informal locality names and
    user-entered `city` values have proven unreliable (e.g. a customer typing
    "Kolkata" for an address that's actually 50+ km away in Nadia district).
    Pincode is the most structured, trustworthy field available.
    """
    candidates = [
        ", ".join(p for p in [pincode, state, "India"] if p),                      # most trustworthy — try first
        ", ".join(p for p in [full_address, pincode, state, "India"] if p),         # full text + pincode, no city
        ", ".join(p for p in [full_address, city, state, pincode, "India"] if p),   # last resort — includes unreliable city
    ]

    for query in candidates:
        if not query.strip():
            continue
        try:
            location = geolocator.geocode(query, timeout=5)
            if location:
                return location.latitude, location.longitude
        except Exception:
            continue

    return None, None