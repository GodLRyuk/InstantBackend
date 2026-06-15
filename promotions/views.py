from django.utils import timezone
from datetime import timedelta
from rest_framework.response import Response  # ✅ fixed — was importing from requests
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from .models import DeliveryPass, Coupon, CouponUsage


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_coupon(request):
    try:
        data = request.data
        code = data.get("code", "").strip().upper()
        order_total = float(data.get("order_total", 0))
    except (TypeError, ValueError):
        return Response({"error": "Invalid request body."}, status=status.HTTP_400_BAD_REQUEST)

    if not code:
        return Response({"error": "Coupon code is required."}, status=status.HTTP_400_BAD_REQUEST)

    # ── Check 1: Members only ──────────────────────────────
    delivery_pass = getattr(request.user, 'delivery_pass', None)
    if not delivery_pass or not delivery_pass.is_valid():
        return Response(
            {"error": "Coupons are available for Pass members only."},
            status=status.HTTP_403_FORBIDDEN
        )

    # ── Check 2: Min order to unlock coupon ───────────────
    from promotions.models import DeliverySettings
    config = DeliverySettings.get()
    if order_total < float(config.coupon_unlock_min):
        shortage = float(config.coupon_unlock_min) - order_total
        return Response(
            {"error": f"Add items worth ₹{shortage:.0f} more to unlock coupons."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ── Check 3: Coupon exists ────────────────────────────
    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return Response({"error": "Coupon not found."}, status=status.HTTP_404_NOT_FOUND)

    # ── Check 4: Active and not expired ──────────────────
    if not coupon.is_valid():
        return Response(
            {"error": "This coupon has expired or is inactive."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ── Check 5: Coupon's own min order ──────────────────
    if order_total < float(coupon.min_order_amount):
        return Response(
            {"error": f"Minimum order of ₹{coupon.min_order_amount} required for this coupon."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ── Check 6: One-time use ─────────────────────────────
    if coupon.one_time_per_user:
        already_used = CouponUsage.objects.filter(
            coupon=coupon, user=request.user
        ).exists()
        if already_used:
            return Response(
                {"error": "You have already used this coupon."},
                status=status.HTTP_400_BAD_REQUEST
            )

    discount = float(coupon.calculate_discount(order_total))

    return Response({
        "success": True,
        "code": coupon.code,
        "coupon_type": coupon.coupon_type,
        "value": float(coupon.value),
        "discount": discount,
        "min_order_amount": float(coupon.min_order_amount),
        "message": f"Coupon applied! You save ₹{discount:.2f}",
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_pass(request):
    user = request.user

    # Already has an active pass?
    existing = getattr(user, 'delivery_pass', None)
    if existing and existing.is_valid():
        return Response(
            {"error": f"You already have an active pass valid until {existing.expires_at.date()}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Load price from DB settings
    from promotions.models import DeliverySettings
    config = DeliverySettings.get()

    expires_at = timezone.now() + timedelta(days=365)

    DeliveryPass.objects.update_or_create(
        user=user,
        defaults={
            "amount_paid": config.pass_price,  # ✅ from DB not hardcoded
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
            "free_delivery_min_order": f"₹{config.free_delivery_min}",
            "coupon_unlock_at": f"₹{config.coupon_unlock_min}",
            "free_deliveries_per_month": config.free_delivery_cap,
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pass_status(request):
    delivery_pass = getattr(request.user, 'delivery_pass', None)

    if not delivery_pass or not delivery_pass.is_valid():
        return Response({"has_pass": False})

    delivery_pass.reset_monthly_count_if_needed()

    from promotions.models import DeliverySettings
    config = DeliverySettings.get()

    return Response({
        "has_pass": True,
        "valid_until": delivery_pass.expires_at.date(),
        "free_deliveries_used_this_month": delivery_pass.free_deliveries_used,
        "free_deliveries_remaining": max(
            0, config.free_delivery_cap - delivery_pass.free_deliveries_used
        ),
        "coupon_unlock_at": config.coupon_unlock_min,
        "free_delivery_min_order": config.free_delivery_min,
    })