from django.contrib.auth import get_user_model
from math import radians, sin, cos, sqrt, atan2

User = get_user_model()


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


def assign_driver(order):

    # ⚠️ SAFETY CHECK 1
    if not hasattr(order, "latitude") or not hasattr(order, "longitude"):
        return User.objects.filter(role="DELIVERY", is_online=True).first()

    drivers = User.objects.filter(
        role="DELIVERY",
        is_online=True
    )

    best_driver = None
    best_score = float("inf")

    for driver in drivers:

        if not driver.latitude or not driver.longitude:
            continue

        distance = calculate_distance(
            order.latitude,
            order.longitude,
            driver.latitude,
            driver.longitude
        )

        active_orders = driver.deliveryassignment_set.filter(
            status__in=["ASSIGNED", "PICKED_UP", "OUT_FOR_DELIVERY"]
        ).count()

        score = distance + (active_orders * 2)

        if score < best_score:
            best_score = score
            best_driver = driver

    # ⚠️ FALLBACK (VERY IMPORTANT)
    if best_driver is None:
        best_driver = drivers.first()

    return best_driver