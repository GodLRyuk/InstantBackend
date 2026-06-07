from .models import Coupon, CouponUsage
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_coupon(request):
    try:
        data = request.data  # ✅ use request.data instead of json.loads(request.body)
        code = data.get("code", "").strip().upper()
        order_total = float(data.get("order_total", 0))
    except (TypeError, ValueError):
        return Response({"error": "Invalid request body."}, status=status.HTTP_400_BAD_REQUEST)

    if not code:
        return Response({"error": "Coupon code is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return Response({"error": "Coupon not found."}, status=status.HTTP_404_NOT_FOUND)

    if not coupon.is_valid():
        return Response({"error": "This coupon has expired or is inactive."}, status=status.HTTP_400_BAD_REQUEST)

    if order_total < float(coupon.min_order_amount):
        return Response(
            {"error": f"Minimum order of ₹{coupon.min_order_amount} required for this coupon."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── One-time-per-user check ────────────────────────
    if coupon.one_time_per_user:
        already_used = CouponUsage.objects.filter(
            coupon=coupon, user=request.user
        ).exists()
        if already_used:
            return Response(
                {"error": "You have already used this coupon."},
                status=status.HTTP_400_BAD_REQUEST,
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