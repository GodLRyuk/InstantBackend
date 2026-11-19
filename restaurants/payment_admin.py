from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PaymentSplit, Restaurant, RestaurantOrder, RestaurantRefund, VendorCommission
from .permissions import IsStaffUser
from .views import ProcessPaymentSplitsView, ProcessRestaurantRefundsView, SyncPaymentSplitsView


class CommissionSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    class Meta:
        model = VendorCommission
        fields = ['id', 'restaurant', 'restaurant_name', 'commission_percentage', 'effective_from']
        extra_kwargs = {'effective_from': {'required': True}}

    @transaction.atomic
    def create(self, data):
        restaurant = Restaurant.objects.select_for_update().get(pk=data['restaurant'].pk)
        existing = VendorCommission.objects.filter(
            restaurant=restaurant, effective_from=data['effective_from'],
        ).order_by('-pk').first()
        if existing is None:
            return VendorCommission.objects.create(**data)
        if existing.commission_percentage != data['commission_percentage']:
            raise ValidationError({'effective_from': 'A different rate already starts at this time.'})
        return existing


class CommissionsView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsStaffUser]
    serializer_class = CommissionSerializer
    queryset = VendorCommission.objects.select_related('restaurant').order_by('-effective_from', '-pk')
    pagination_class = None


class SplitSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number')
    restaurant_name = serializers.CharField(source='order.restaurant.name')
    status = serializers.CharField(source='cashfree_split_status')
    provider_reference = serializers.CharField(source='settlement_id')

    class Meta:
        model = PaymentSplit
        fields = ['id', 'order_number', 'restaurant_name', 'gross_amount', 'commission_percentage',
                  'platform_commission', 'vendor_amount', 'status', 'provider_reference']


class RefundSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number')
    restaurant_name = serializers.CharField(source='order.restaurant.name')
    provider_reference = serializers.CharField(source='cashfree_refund_id')

    class Meta:
        model = RestaurantRefund
        fields = ['id', 'order_number', 'restaurant_name', 'amount', 'status', 'provider_reference']


class OrderNumberSerializer(serializers.Serializer):
    order_number = serializers.CharField(max_length=32)


class PaymentRecordsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsStaffUser]
    pagination_class = None

    def get_queryset(self):
        records = super().get_queryset()
        order_number = self.request.query_params.get('order_number', '').strip()
        if order_number:
            records = records.filter(order__order_number__iexact=order_number)
        return records[:100]

    def lock_order(self, request):
        serializer = OrderNumberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = get_object_or_404(
            RestaurantOrder.objects.select_for_update(),
            order_number=serializer.validated_data['order_number'].upper(),
        )
        if order.payment_method != RestaurantOrder.PaymentMethod.ONLINE or not order.cashfree_order_id:
            raise ValidationError({'order_number': 'Select an online Cashfree order.'})
        return order


class SplitsView(PaymentRecordsView):
    serializer_class = SplitSerializer
    queryset = PaymentSplit.objects.select_related('order__restaurant').order_by('-pk')

    def post(self, request):
        with transaction.atomic():
            order = self.lock_order(request)
            split = PaymentSplit.objects.filter(order=order).first()
            if split is None:
                if order.payment_status != RestaurantOrder.PaymentStatus.PAID:
                    raise ValidationError({'order_number': 'The Cashfree order must be paid.'})
                vendor = getattr(order.restaurant, 'vendor', None)
                if not vendor or not vendor.cashfree_vendor_id:
                    raise ValidationError({'order_number': 'Register the restaurant vendor with Cashfree first.'})
                commission = order.restaurant.commissions.filter(
                    effective_from__lte=order.created_at,
                ).first()
                rate = commission.commission_percentage if commission else Decimal('0')
                gross = order.total_amount
                platform_share = (gross * rate / Decimal('100')).quantize(Decimal('0.01'))
                # For orders without a split, start the provider's waiting period
                # from this confirmed paid state.
                split = PaymentSplit.objects.create(
                    order=order, vendor=vendor, gross_amount=gross, platform_commission=platform_share,
                    vendor_amount=gross - platform_share, commission_percentage=rate, paid_at=timezone.now(),
                )
            if (split.paid_at is None and order.payment_status == RestaurantOrder.PaymentStatus.PAID
                    and split.cashfree_split_status == PaymentSplit.Status.PENDING):
                split.paid_at = timezone.now()
                split.save(update_fields=['paid_at', 'updated_at'])

        result = None
        if split.cashfree_split_status in [PaymentSplit.Status.SUBMITTED, PaymentSplit.Status.SETTLED]:
            result = SyncPaymentSplitsView.run(order.pk)
        elif split.paid_at and split.paid_at <= timezone.now() - timedelta(minutes=2):
            result = ProcessPaymentSplitsView.run(order.pk)
        split.refresh_from_db()
        return Response({**self.get_serializer(split).data, 'cashfree_error': bool(result and result.data['failed'])})


class RefundsView(PaymentRecordsView):
    serializer_class = RefundSerializer
    queryset = RestaurantRefund.objects.select_related('order__restaurant').order_by('-pk')

    def post(self, request):
        with transaction.atomic():
            order = self.lock_order(request)
            refund = RestaurantRefund.objects.filter(order=order).first()
            if refund is None:
                if (order.status not in [RestaurantOrder.Status.CANCELLED, RestaurantOrder.Status.REJECTED]
                        or order.payment_status != RestaurantOrder.PaymentStatus.REFUND_PENDING):
                    raise ValidationError({'order_number': 'Select a cancelled or rejected order awaiting a refund.'})
                refund = RestaurantRefund.objects.create(
                    order=order, refund_id=f'rorefund{order.pk}', amount=order.total_amount,
                )

        result = ProcessRestaurantRefundsView.run(order.pk)
        refund.refresh_from_db()
        return Response({**self.get_serializer(refund).data, 'cashfree_error': bool(result.data['failed'])})
