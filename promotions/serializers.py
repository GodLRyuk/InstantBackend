from rest_framework import serializers

from .models import Coupon


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "coupon_type",
            "value",
            "min_order_amount",
            "active",
            "expires_at",
            "one_time_per_user",
        ]

    def validate_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        code = attrs.get("code", getattr(self.instance, "code", ""))
        existing_codes = Coupon.objects.filter(code=code)
        if self.instance:
            existing_codes = existing_codes.exclude(pk=self.instance.pk)
        if existing_codes.exists():
            raise serializers.ValidationError(
                {"code": "A coupon with this code already exists."}
            )
        return attrs
