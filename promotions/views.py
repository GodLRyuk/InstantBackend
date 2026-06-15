from django.utils import timezone
from datetime import timedelta

from requests import Response
from .models import DeliveryPass
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_pass(request):
    user = request.user

    # Already has an active pass?
    existing = getattr(user, 'delivery_pass', None)
    if existing and existing.is_valid():
        return Response(
            {"error": f"You already have an active pass valid until {existing.expires_at.date()}"},
            status=400
        )

    # Create or renew
    expires_at = timezone.now() + timedelta(days=365)

    DeliveryPass.objects.update_or_create(
        user=user,
        defaults={
            "amount_paid": 1499,
            "expires_at": expires_at,
            "is_active": True,
            "free_deliveries_used": 0,
        }
    )

    return Response({
        "success": True,
        "message": "Delivery Pass activated!",
        "valid_until": expires_at.date(),
        "benefits": {
            "free_delivery_min_order": f"₹{DeliveryPass.MIN_ORDER_DELIVERY}",
            "coupon_unlock_at": f"₹{DeliveryPass.MIN_ORDER_COUPON}",
            "free_deliveries_per_month": DeliveryPass.FREE_DELIVERY_CAP,
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pass_status(request):
    delivery_pass = getattr(request.user, 'delivery_pass', None)

    if not delivery_pass or not delivery_pass.is_valid():
        return Response({"has_pass": False})

    delivery_pass.reset_monthly_count_if_needed()

    return Response({
        "has_pass": True,
        "valid_until": delivery_pass.expires_at.date(),
        "free_deliveries_used_this_month": delivery_pass.free_deliveries_used,
        "free_deliveries_remaining": max(
            0, DeliveryPass.FREE_DELIVERY_CAP - delivery_pass.free_deliveries_used
        ),
        "coupon_unlock_at": DeliveryPass.MIN_ORDER_COUPON,
        "free_delivery_min_order": DeliveryPass.MIN_ORDER_DELIVERY,
    })