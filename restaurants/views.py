from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from decimal import Decimal
import hmac
import re
from django.utils import timezone
from rest_framework import generics, mixins, status as http, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    Cuisine,
    MenuCategory,
    MenuItem,
    Restaurant,
    RestaurantDeliveryAssignment,
    RestaurantOrder,
    RestaurantVendor,
    PaymentSplit,
    RestaurantRefund,
)
from .permissions import IsStaffUser
from .serializers import (
    AdminRestaurantSerializer,
    AdminMenuCategorySerializer,
    CuisineSerializer,
    DeliveryChargeSerializer,
    MenuCategorySerializer,
    MenuItemSerializer,
    OrderSerializer,
    PartnerMenuItemSerializer,
    PartnerRestaurantSerializer,
    PlaceOrderSerializer,
    QuoteSerializer,
    RestaurantDetailSerializer,
    RestaurantListSerializer,
    StatusChangeSerializer,
    VerifyPaymentSerializer,
)

S = RestaurantOrder.Status
P = RestaurantOrder.PaymentStatus
M = RestaurantOrder.PaymentMethod

MAX_RADIUS_KM = 15  # restaurants farther than this are hidden when the app sends lat/lng
ACTIVE_STATUSES = [S.PLACED, S.ACCEPTED, S.PREPARING, S.READY, S.OUT_FOR_DELIVERY]


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value):
    return f'{value:.2f}'


# =========================================================== customer: browse
class CuisineListView(generics.ListAPIView):
    queryset = Cuisine.objects.all()
    serializer_class = CuisineSerializer
    pagination_class = None


class DeliveryChargeView(APIView):
    """Calculate delivery fee and availability before a customer places an order."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeliveryChargeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            restaurant = Restaurant.objects.get(
                pk=data['restaurant_id'],
                status=Restaurant.Status.APPROVED,
            )
        except Restaurant.DoesNotExist:
            raise ValidationError({'restaurant_id': 'Restaurant not found.'})

        address = services.resolve_address(request.user, data['address_id'])
        coordinates = (address['lat'], address['lng'], restaurant.latitude, restaurant.longitude)
        if any(value is None for value in coordinates):
            raise ValidationError({
                'address_id': 'Delivery distance cannot be calculated because location coordinates are missing.'
            })

        distance_km = services.haversine_km(
            address['lat'], address['lng'], restaurant.latitude, restaurant.longitude
        )
        radius_km = float(restaurant.delivery_radius_km)
        if distance_km > radius_km:
            return Response(
                {
                    'serving_area': False,
                    'message': 'Sorry, we are not serving this area yet.',
                    'distance_km': round(distance_km, 2),
                    'service_radius_km': radius_km,
                },
                status=http.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'serving_area': True,
            'message': 'Delivery is available at this address.',
            'distance_km': round(distance_km, 2),
            'service_radius_km': radius_km,
            'delivery_fee': _money(services.calculate_delivery_charge(restaurant, distance_km)),
        })


class RestaurantViewSet(mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """GET /api/restaurants/?q=&cuisine=&lat=&lng=   and   /{id}/   and   /{id}/menu/"""

    lookup_value_regex = r'\d+'
    pagination_class = None

    def get_queryset(self):
        if (
            self.request.user.is_authenticated
            and getattr(self.request.user, 'role', None) == 'RESTAURANT'
        ):
            return Restaurant.objects.filter(owner=self.request.user).prefetch_related('cuisines')
        return Restaurant.objects.filter(status=Restaurant.Status.APPROVED).prefetch_related(
            'cuisines'
        )

    def get_serializer_class(self):
        if (
            self.request.user.is_authenticated
            and getattr(self.request.user, 'role', None) == 'RESTAURANT'
        ):
            return PartnerRestaurantSerializer
        return RestaurantDetailSerializer if self.action == 'retrieve' else RestaurantListSerializer

    def _geo(self):
        p = self.request.query_params
        lat, lng = _float(p.get('lat')), _float(p.get('lng'))
        return (lat, lng) if lat is not None and lng is not None else (None, None)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['lat'], ctx['lng'] = self._geo()
        return ctx

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        if request.user.is_authenticated and getattr(request.user, 'role', None) == 'RESTAURANT':
            restaurants = list(qs)
            return Response(self.get_serializer(restaurants, many=True).data)

        q = request.query_params.get('q', '').strip()
        cuisine = request.query_params.get('cuisine', '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(cuisines__name__icontains=q)
                | Q(items__name__icontains=q, items__is_available=True)
            )
        if cuisine:
            qs = qs.filter(
                Q(cuisines__id=int(cuisine)) if cuisine.isdigit() else Q(cuisines__name__iexact=cuisine)
            )
        restaurants = list(qs.distinct())

        lat, lng = self._geo()
        if lat is not None:
            restaurants = [
                r for r in restaurants
                if (d := r.distance_from(lat, lng)) is None or d <= MAX_RADIUS_KM
            ]
        restaurants.sort(
            key=lambda r: (
                not r.is_open_now,
                r.distance_from(lat, lng) if r.distance_from(lat, lng) is not None else 9999,
                r.name,
            )
        )
        return Response(self.get_serializer(restaurants, many=True).data)

    @action(detail=True, methods=['get'])
    def menu(self, request, pk=None):
        restaurant = self.get_object()
        items = restaurant.items.select_related('category').order_by(
            'category__sort_order', 'sort_order', 'name'
        )
        return Response(MenuItemSerializer(items, many=True, context={'request': request}).data)

    def update(self, request, *args, **kwargs):
        require_restaurant_owner(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        require_restaurant_owner(request)
        return super().partial_update(request, *args, **kwargs)


# =========================================================== customer: orders
class CustomerOrderViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """My restaurant orders, bill quote, place order, cancel, verify payment."""

    serializer_class = OrderSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            RestaurantOrder.objects.filter(customer=self.request.user)
            .select_related('restaurant')
            .prefetch_related('items')
        )

    @action(detail=False, methods=['post'])
    def quote(self, request):
        """Price a cart on the server before showing the pay button."""
        s = QuoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        quote = services.build_quote(request.user, d['restaurant_id'], d['items'], d.get('address_id'))
        bill = quote['bill']
        return Response(
            {
                'restaurant_id': quote['restaurant'].id,
                'distance_km': quote['distance_km'],
                'item_total': _money(bill.item_total),
                'discount': _money(bill.discount),
                'delivery_fee': _money(bill.delivery_fee),
                'packaging_charge': _money(bill.packaging),
                'gst': _money(bill.gst),
                'total_amount': _money(bill.total),
                'offer_code': quote['restaurant'].offer_code if bill.discount > 0 else '',
            }
        )

    def create(self, request):
        s = PlaceOrderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        quote = services.build_quote(request.user, d['restaurant_id'], d['items'], d['address_id'])
        order = services.create_order(request.user, quote, d['payment_method'], d.get('notes', ''))
        data = OrderSerializer(order, context={'request': request}).data
        if order.payment_method == M.ONLINE:
            from django.conf import settings

            data['cashfree'] = {
                'environment': settings.CASHFREE_ENV,
                'order_id': order.cashfree_order_id,
                'payment_session_id': order.cashfree_payment_session_id,
                'amount': str(order.total_amount),
                'currency': 'INR',
            }
        return Response(data, status=http.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = services.change_status(
            pk,
            S.CANCELLED,
            reason=str(request.data.get('reason', ''))[:255],
            allow={S.AWAITING_PAYMENT, S.PLACED},
            customer=request.user,
        )
        return Response(OrderSerializer(order, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='verify-payment')
    def verify_payment(self, request, pk=None):
        s = VerifyPaymentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            order = get_object_or_404(
                RestaurantOrder.objects.select_for_update(), pk=pk, customer=request.user
            )
            if order.payment_method != M.ONLINE or not order.cashfree_order_id:
                raise ValidationError({'detail': 'This order is not an online payment order.'})
            if order.payment_status != P.PAID:
                try:
                    payment = services.cashfree.success_payment(order.cashfree_order_id)
                except Exception as exc:
                    raise ValidationError({'detail': 'Could not verify payment with Cashfree.'}) from exc
                if not payment or Decimal(str(payment.get('payment_amount', 0))) != order.total_amount:
                    raise ValidationError({'detail': 'Payment verification failed.'})
                order.payment_status = P.PAID
                order.cashfree_payment_id = str(payment.get('cf_payment_id', ''))
                split = getattr(order, 'payment_split', None)
                if split and not split.paid_at:
                    split.paid_at = timezone.now()
                    split.save(update_fields=['paid_at', 'updated_at'])
                if order.status == S.AWAITING_PAYMENT:
                    order.status = S.PLACED
                    services.notify_restaurant_owner_order_placed(order)
                order.save()
        return Response(OrderSerializer(order, context={'request': request}).data)


# =========================================================== partner (restaurant owner)
def require_restaurant_owner(request):
    if request.user.role != 'RESTAURANT':
        raise PermissionDenied('A restaurant owner account is required.')


def partner_restaurant(request):
    require_restaurant_owner(request)
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    if restaurant is None:
        raise NotFound('No restaurant is registered for this account.')
    return restaurant


class PartnerOnboardView(APIView):
    """POST /api/restaurants/partner/onboard/  (multipart, so logo and cover can be sent)."""

    def post(self, request):
        require_restaurant_owner(request)
        if Restaurant.objects.filter(owner=request.user).exists():
            return Response(
                {'detail': 'You already have a restaurant registered.'},
                status=http.HTTP_400_BAD_REQUEST,
            )
        s = PartnerRestaurantSerializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        s.save(owner=request.user, status=Restaurant.Status.PENDING)
        return Response(s.data, status=http.HTTP_201_CREATED)


class AdminRestaurantVendorView(APIView):
    """Staff API used by the Angular admin panel to onboard Cashfree vendors."""
    permission_classes = [IsAuthenticated, IsStaffUser]

    @staticmethod
    def _serialize(vendor):
        return {
            'id': vendor.pk,
            'restaurant_id': vendor.restaurant_id,
            'restaurant_name': vendor.restaurant.name,
            'cashfree_vendor_id': vendor.cashfree_vendor_id,
            'verification_status': vendor.verification_status,
            'settlement_status': vendor.settlement_status,
            'bank_account_last4': vendor.bank_account_number[-4:],
            'ifsc_code': vendor.ifsc_code,
            'updated_at': vendor.updated_at,
        }

    def get(self, request):
        vendors = RestaurantVendor.objects.select_related('restaurant').order_by('restaurant__name')
        return Response([self._serialize(vendor) for vendor in vendors])

    def post(self, request):
        data = request.data
        restaurant_id = data.get('restaurant_id')
        try:
            restaurant = Restaurant.objects.select_related('owner').get(pk=restaurant_id)
        except (Restaurant.DoesNotExist, TypeError, ValueError):
            raise ValidationError({'restaurant_id': 'Select a valid restaurant.'})
        if restaurant.status != Restaurant.Status.APPROVED:
            raise ValidationError({'restaurant_id': 'Restaurant approval is required before vendor onboarding.'})

        required = ('account_number', 'ifsc_code', 'account_holder_name', 'pan')
        missing = [key for key in required if not str(data.get(key, '')).strip()]
        if missing:
            raise ValidationError({key: 'This field is required.' for key in missing})
        account = str(data['account_number']).strip()
        if not account.isdigit() or not 6 <= len(account) <= 18:
            raise ValidationError({'account_number': 'Enter a bank account number of 6–18 digits.'})
        ifsc = str(data['ifsc_code']).strip().upper()
        if not re.fullmatch(r'[A-Z]{4}0[A-Z0-9]{6}', ifsc):
            raise ValidationError({'ifsc_code': 'Enter a valid IFSC code.'})
        holder = str(data['account_holder_name']).strip()
        pan = str(data['pan']).strip().upper()
        if not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', pan):
            raise ValidationError({'pan': 'Enter a valid PAN.'})
        # This endpoint onboards restaurants, so send Cashfree's accepted
        # industry category rather than arbitrary restaurant/legal-form text.
        business_type = 'Food and Beverages'
        gstin = str(data.get('gstin', '')).strip().upper()
        if gstin and not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]', gstin):
            raise ValidationError({'gstin': 'Enter a valid GSTIN.'})
        email = restaurant.email or restaurant.owner.email
        phone = restaurant.phone or getattr(restaurant.owner, 'phone', '')
        if not email or not phone:
            raise ValidationError({'detail': 'Restaurant email and phone are required for Cashfree onboarding.'})

        with transaction.atomic():
            vendor = RestaurantVendor.objects.select_for_update().filter(restaurant=restaurant).first()
            if vendor and vendor.cashfree_vendor_id:
                raise ValidationError({'detail': 'This restaurant already has a Cashfree vendor.'})
            if vendor is None:
                vendor = RestaurantVendor(restaurant=restaurant)
            vendor.bank_account_number = account
            vendor.ifsc_code = ifsc
            vendor.account_holder_name = holder
            vendor.pan = pan
            vendor.business_type = business_type
            vendor.gstin = gstin
            vendor.save()
            vendor_id = f'restaurant_{restaurant.pk}'
            try:
                result = services.cashfree.create_vendor(
                    vendor_id=vendor_id, name=restaurant.name, email=email, phone=phone,
                    account_number=account, account_holder=holder, ifsc=ifsc,
                    pan=pan, business_type=business_type, gstin=gstin,
                )
            except Exception as exc:
                provider_error = services.cashfree.safe_error_details(
                    exc, sensitive_values=(account, pan, gstin, holder, phone)
                )
                return Response(
                    {
                        'detail': 'Vendor details were saved, but Cashfree registration failed. Retry this request after resolving the provider error.',
                        'cashfree_error': provider_error,
                    },
                    status=http.HTTP_502_BAD_GATEWAY,
                )
            vendor.cashfree_vendor_id = vendor_id
            vendor.verification_status = result.get('status', 'PENDING')
            vendor.last_cashfree_response = result
            vendor.save(update_fields=['cashfree_vendor_id', 'verification_status',
                                       'last_cashfree_response', 'updated_at'])
        return Response(self._serialize(vendor), status=http.HTTP_201_CREATED)


class ProcessPaymentSplitsView(APIView):
    """Cron-triggerable endpoint: submit paid orders after Cashfree's two-minute delay."""
    permission_classes = [IsAuthenticated, IsStaffUser]

    def post(self, request):
        from datetime import timedelta
        from django.utils import timezone
        processed = 0
        failed = 0
        due = PaymentSplit.objects.select_related('order', 'vendor').filter(
            cashfree_split_status__in=[PaymentSplit.Status.PENDING, PaymentSplit.Status.FAILED],
            paid_at__lte=timezone.now() - timedelta(minutes=2),
            order__payment_status=RestaurantOrder.PaymentStatus.PAID,
        ).order_by('paid_at')[:100]
        for candidate in due:
            with transaction.atomic():
                split = PaymentSplit.objects.select_for_update().get(pk=candidate.pk)
                if split.cashfree_split_status not in [PaymentSplit.Status.PENDING, PaymentSplit.Status.FAILED]:
                    continue
                split.cashfree_split_status = PaymentSplit.Status.PROCESSING
                split.save(update_fields=['cashfree_split_status', 'updated_at'])
            try:
                result = services.cashfree.submit_order_split(
                    split.order.cashfree_order_id,
                    vendor_id=split.vendor.cashfree_vendor_id,
                    vendor_percentage=Decimal('100') - split.commission_percentage,
                )
                split.cashfree_response = result
                split.cashfree_split_status = PaymentSplit.Status.SUBMITTED
                split.save(update_fields=['cashfree_response', 'cashfree_split_status', 'updated_at'])
                RestaurantVendor.objects.filter(pk=split.vendor_id).update(settlement_status='IN_PROGRESS')
                processed += 1
            except Exception:
                split.cashfree_split_status = PaymentSplit.Status.FAILED
                split.save(update_fields=['cashfree_split_status', 'updated_at'])
                failed += 1
        return Response({'processed': processed, 'failed': failed})


class SyncPaymentSplitsView(APIView):
    """Refresh Cashfree split and settlement references for submitted restaurant orders."""
    permission_classes = [IsAuthenticated, IsStaffUser]

    def post(self, request):
        synced = 0
        failed = 0
        splits = PaymentSplit.objects.select_related('order', 'vendor').filter(
            cashfree_split_status__in=[PaymentSplit.Status.SUBMITTED, PaymentSplit.Status.SETTLED]
        ).order_by('updated_at')[:100]
        for split in splits:
            try:
                details = services.cashfree.get_order_split_details(split.order.cashfree_order_id)
            except Exception:
                failed += 1
                continue
            vendors = details.get('vendors') or []
            vendor_details = next((item for item in vendors
                                   if item.get('vendor_id') == split.vendor.cashfree_vendor_id), {})
            settlement_id = vendor_details.get('settlement_id')
            if settlement_id:
                split.settlement_id = str(settlement_id)
            vendor_status = str(vendor_details.get('status', '')).upper()
            if vendor_status in {'SUCCESS', 'SETTLED'}:
                split.cashfree_split_status = PaymentSplit.Status.SETTLED
                RestaurantVendor.objects.filter(pk=split.vendor_id).update(settlement_status='SETTLED')
            split.cashfree_response = details
            split.save(update_fields=['settlement_id', 'cashfree_split_status',
                                      'cashfree_response', 'updated_at'])
            synced += 1
        return Response({'synced': synced, 'failed': failed})


class ProcessRestaurantRefundsView(APIView):
    """Initiate cancellation refunds and reconcile their Cashfree status."""
    permission_classes = [IsAuthenticated, IsStaffUser]

    def post(self, request):
        processed = 0
        failed = 0
        refunds = RestaurantRefund.objects.select_related('order').filter(
            status__in=[RestaurantRefund.Status.PENDING, RestaurantRefund.Status.FAILED],
            order__payment_status=RestaurantOrder.PaymentStatus.REFUND_PENDING,
        ).order_by('created_at')[:100]
        for candidate in refunds:
            with transaction.atomic():
                refund = RestaurantRefund.objects.select_for_update().select_related(
                    'order', 'order__payment_split', 'order__payment_split__vendor'
                ).get(pk=candidate.pk)
                if refund.status not in [RestaurantRefund.Status.PENDING, RestaurantRefund.Status.FAILED]:
                    continue
                refund.status = RestaurantRefund.Status.PROCESSING
                refund.save(update_fields=['status', 'updated_at'])
            split = getattr(refund.order, 'payment_split', None)
            refund_splits = None
            if split and split.cashfree_split_status in [PaymentSplit.Status.SUBMITTED, PaymentSplit.Status.SETTLED]:
                refund_splits = [{'vendor_id': split.vendor.cashfree_vendor_id,
                                  'amount': float(split.vendor_amount)}]
            try:
                result = services.cashfree.create_refund(
                    refund.order.cashfree_order_id,
                    refund_id=refund.refund_id,
                    amount=refund.amount,
                    note=refund.order.rejection_reason or 'Restaurant order cancelled',
                    refund_splits=refund_splits,
                )
                refund.cashfree_refund_id = str(result.get('cf_refund_id', ''))
                refund.cashfree_response = result
                status_value = str(result.get('refund_status', 'PENDING')).upper()
                refund.status = (RestaurantRefund.Status.SUCCESS if status_value == 'SUCCESS'
                                 else RestaurantRefund.Status.SUBMITTED if status_value in {'PENDING', 'QUEUED'}
                                 else RestaurantRefund.Status.FAILED)
                refund.save(update_fields=['cashfree_refund_id', 'cashfree_response', 'status', 'updated_at'])
                if refund.status == RestaurantRefund.Status.SUCCESS:
                    RestaurantOrder.objects.filter(pk=refund.order_id).update(
                        payment_status=RestaurantOrder.PaymentStatus.REFUNDED)
                processed += 1
            except Exception:
                refund.status = RestaurantRefund.Status.FAILED
                refund.save(update_fields=['status', 'updated_at'])
                failed += 1
        # Poll existing refunds in the same cron pass.
        pending = RestaurantRefund.objects.select_related('order').filter(
            status=RestaurantRefund.Status.SUBMITTED
        ).order_by('updated_at')[:100]
        synced = 0
        for refund in pending:
            try:
                result = services.cashfree.get_refund(refund.order.cashfree_order_id, refund.refund_id)
            except Exception:
                failed += 1
                continue
            refund.cashfree_response = result
            value = str(result.get('refund_status', '')).upper()
            if value == 'SUCCESS':
                refund.status = RestaurantRefund.Status.SUCCESS
                RestaurantOrder.objects.filter(pk=refund.order_id).update(
                    payment_status=RestaurantOrder.PaymentStatus.REFUNDED)
            elif value in {'FAILED', 'CANCELLED'}:
                refund.status = RestaurantRefund.Status.FAILED
            refund.save(update_fields=['cashfree_response', 'status', 'updated_at'])
            synced += 1
        return Response({'processed': processed, 'failed': failed, 'synced': synced})


class PartnerBaseMixin:
    pagination_class = None

    @property
    def restaurant(self):
        if not hasattr(self, '_restaurant'):
            self._restaurant = partner_restaurant(self.request)
        return self._restaurant

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['restaurant'] = self.restaurant
        return ctx


class PartnerCategoryViewSet(PartnerBaseMixin, viewsets.ModelViewSet):
    serializer_class = MenuCategorySerializer

    def get_queryset(self):
        return MenuCategory.objects.filter(restaurant=self.restaurant)

    def perform_create(self, serializer):
        serializer.save(restaurant=self.restaurant)


class PartnerItemViewSet(PartnerBaseMixin, viewsets.ModelViewSet):
    """Dishes. Send multipart when uploading an image."""

    parser_classes = [JSONParser, FormParser, MultiPartParser]
    serializer_class = PartnerMenuItemSerializer

    def get_queryset(self):
        qs = MenuItem.objects.filter(restaurant=self.restaurant).select_related('category')
        category = self.request.query_params.get('category')
        if category and category.isdigit():
            qs = qs.filter(category_id=int(category))
        return qs

    def perform_create(self, serializer):
        serializer.save(restaurant=self.restaurant)

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """In stock / out of stock. Body {"is_available": true|false} or empty to flip."""
        item = self.get_object()
        value = request.data.get('is_available')
        item.is_available = (not item.is_available) if value is None else str(value).lower() in (
            'true', '1', 'yes',
        )
        item.save(update_fields=['is_available', 'updated_at'])
        return Response(self.get_serializer(item).data)


class OrderFilterMixin:
    def filter_orders(self, qs):
        p = self.request.query_params
        if p.get('active') in ('1', 'true'):
            qs = qs.filter(status__in=ACTIVE_STATUSES)
        statuses = [s for s in p.get('status', '').split(',') if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        return qs


class PartnerOrderViewSet(PartnerBaseMixin, OrderFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Incoming orders. ?active=1 or ?status=placed,accepted"""

    serializer_class = OrderSerializer

    def get_queryset(self):
        qs = (
            RestaurantOrder.objects.filter(restaurant=self.restaurant)
            .exclude(status=S.AWAITING_PAYMENT)
            .select_related('restaurant')
            .prefetch_related('items')
        )
        return self.filter_orders(qs)

    @action(detail=True, methods=['post'])
    def status(self, request, pk=None):
        """Body {"status": "accepted|rejected|preparing|ready", "reason": ""}"""
        s = StatusChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        order = services.change_status(
            pk,
            s.validated_data['status'],
            reason=s.validated_data.get('reason', ''),
            restaurant=self.restaurant,
        )
        data = OrderSerializer(order, context={'request': request}).data
        if s.validated_data['status'] == S.ACCEPTED:
            assignment = RestaurantDeliveryAssignment.objects.filter(order=order).first()
            data['delivery_assignment'] = (
                {
                    'id': assignment.id,
                    'driver_id': assignment.driver_id,
                    'status': assignment.status,
                }
                if assignment
                else {'status': 'unassigned', 'driver_id': None}
            )
        return Response(data)


class RestaurantDriverOrdersView(APIView):
    """Restaurant orders assigned to the authenticated delivery agent."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ('DELIVERY', 'PICKUP'):
            raise PermissionDenied('A delivery agent account is required.')
        assignments = (
            RestaurantDeliveryAssignment.objects.filter(driver=request.user)
            .select_related('order', 'order__restaurant')
            .prefetch_related('order__items')
        )
        return Response([self._serialize_assignment(assignment) for assignment in assignments])

    @staticmethod
    def _serialize_assignment(assignment):
        order = assignment.order
        return {
            'assignment_id': assignment.id,
            'order_type': 'restaurant',
            'order_id': order.id,
            'order_number': order.order_number,
            'order_status': order.status,
            'payment_status': order.payment_status,
            'payment_method': order.payment_method,
            'total_amount': order.total_amount,
            'delivery_otp': order.delivery_otp,
            'customer_name': order.customer_name,
            'customer_phone': order.customer_phone,
            'address': order.delivery_address,
            'restaurant': {
                'id': order.restaurant_id,
                'name': order.restaurant.name,
                'phone': order.restaurant.phone,
                'address_line': order.restaurant.address_line,
                'city': order.restaurant.city,
            },
            'items': [
                {
                    'name': item.name,
                    'quantity': item.quantity,
                    'is_veg': item.is_veg,
                }
                for item in order.items.all()
            ],
            'assigned_at': assignment.assigned_at,
            'assignment_status': assignment.status,
        }


class RestaurantDriverOrderDetailView(APIView):
    """Retrieve or update a restaurant order assigned to the current driver."""

    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        if request.user.role not in ('DELIVERY', 'PICKUP'):
            raise PermissionDenied('A delivery agent account is required.')
        assignment = get_object_or_404(
            RestaurantDeliveryAssignment.objects.select_related('order', 'order__restaurant')
            .prefetch_related('order__items'),
            order_id=order_id,
            driver=request.user,
        )
        return Response(RestaurantDriverOrdersView._serialize_assignment(assignment))

    @transaction.atomic
    def post(self, request, order_id):
        if request.user.role not in ('DELIVERY', 'PICKUP'):
            raise PermissionDenied('A delivery agent account is required.')

        assignment = get_object_or_404(
            RestaurantDeliveryAssignment.objects.select_for_update(),
            order_id=order_id,
            driver=request.user,
        )
        requested_status = request.data.get('status')
        transitions = {
            'picked_up': S.OUT_FOR_DELIVERY,
            'delivered': S.DELIVERED,
        }
        new_status = transitions.get(requested_status)
        if new_status is None:
            raise ValidationError({
                'status': 'Expected either "picked_up" or "delivered".',
            })

        if new_status == S.DELIVERED:
            order = RestaurantOrder.objects.select_for_update().get(pk=order_id)
            otp = request.data.get('otp')
            if not isinstance(otp, str) or len(otp) != 6 or not otp.isascii() or not otp.isdigit():
                raise ValidationError({'otp': 'A 6-digit OTP is required to complete delivery.'})
            if not hmac.compare_digest(order.delivery_otp, otp):
                raise ValidationError({'otp': 'Invalid delivery OTP.'})
            if order.delivery_otp_verified:
                raise ValidationError({'otp': 'Delivery OTP has already been used.'})
            order.delivery_otp_verified = True
            order.save(update_fields=['delivery_otp_verified'])

        order = services.change_status(
            order_id,
            new_status,
            staff=True,
        )
        return Response(OrderSerializer(order, context={'request': request}).data)


# =========================================================== admin (Instant team)
class AdminCuisineViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffUser]
    serializer_class = CuisineSerializer
    queryset = Cuisine.objects.all()
    pagination_class = None


class AdminMenuCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffUser]
    serializer_class = AdminMenuCategorySerializer
    pagination_class = None

    def get_queryset(self):
        queryset = MenuCategory.objects.select_related('restaurant')
        restaurant_id = self.request.query_params.get('restaurant')
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        return queryset


class AdminRestaurantViewSet(viewsets.ModelViewSet):
    """Review and onboard restaurants. ?status=pending  ?q=name"""

    permission_classes = [IsStaffUser]
    serializer_class = AdminRestaurantSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Restaurant.objects.select_related('owner').prefetch_related('cuisines')
        p = self.request.query_params
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('q'):
            qs = qs.filter(name__icontains=p['q'])
        return qs.order_by('-created_at')

    def _set_status(self, request, new_status, reason=''):
        restaurant = self.get_object()
        restaurant.status = new_status
        restaurant.rejection_reason = reason
        restaurant.save(update_fields=['status', 'rejection_reason', 'updated_at'])
        return Response(self.get_serializer(restaurant).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._set_status(request, Restaurant.Status.APPROVED)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        reason = str(request.data.get('reason', '')).strip()
        if not reason:
            raise ValidationError({'reason': 'Please give a reason.'})
        return self._set_status(request, Restaurant.Status.REJECTED, reason[:255])

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        return self._set_status(
            request, Restaurant.Status.SUSPENDED, str(request.data.get('reason', ''))[:255]
        )


class AdminOrderViewSet(OrderFilterMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsStaffUser]
    serializer_class = OrderSerializer
    pagination_class = None

    def get_queryset(self):
        qs = RestaurantOrder.objects.select_related('restaurant').prefetch_related('items')
        restaurant = self.request.query_params.get('restaurant')
        if restaurant and restaurant.isdigit():
            qs = qs.filter(restaurant_id=int(restaurant))
        return self.filter_orders(qs)

    @action(detail=True, methods=['post'])
    def status(self, request, pk=None):
        s = StatusChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        order = services.change_status(
            pk, s.validated_data['status'], staff=True, reason=s.validated_data.get('reason', '')
        )
        return Response(OrderSerializer(order, context={'request': request}).data)
