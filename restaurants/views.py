from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, status as http, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Cuisine, MenuCategory, MenuItem, Restaurant, RestaurantOrder
from .permissions import IsStaffUser
from .serializers import (
    AdminRestaurantSerializer,
    AdminMenuCategorySerializer,
    CuisineSerializer,
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


class RestaurantViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/restaurants/?q=&cuisine=&lat=&lng=   and   /{id}/   and   /{id}/menu/"""

    lookup_value_regex = r'\d+'
    pagination_class = None

    def get_queryset(self):
        return Restaurant.objects.filter(status=Restaurant.Status.APPROVED).prefetch_related(
            'cuisines'
        )

    def get_serializer_class(self):
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

            data['razorpay'] = {
                'key_id': settings.RAZORPAY_KEY_ID,
                'order_id': order.razorpay_order_id,
                'amount': int(order.total_amount * 100),  # paise
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
            if order.payment_method != M.ONLINE or not order.razorpay_order_id:
                raise ValidationError({'detail': 'This order is not an online payment order.'})
            if order.payment_status != P.PAID:
                ok = services.verify_razorpay_signature(
                    order.razorpay_order_id,
                    s.validated_data['razorpay_payment_id'],
                    s.validated_data['razorpay_signature'],
                )
                if not ok:
                    raise ValidationError({'detail': 'Payment verification failed.'})
                order.payment_status = P.PAID
                order.razorpay_payment_id = s.validated_data['razorpay_payment_id']
                if order.status == S.AWAITING_PAYMENT:
                    order.status = S.PLACED
                order.save()
        return Response(OrderSerializer(order, context={'request': request}).data)


# =========================================================== partner (restaurant owner)
def partner_restaurant(request):
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    if restaurant is None:
        raise NotFound('No restaurant is registered for this account.')
    return restaurant


class PartnerOnboardView(APIView):
    """POST /api/restaurants/partner/onboard/  (multipart, so logo and cover can be sent)."""

    def post(self, request):
        if Restaurant.objects.filter(owner=request.user).exists():
            return Response(
                {'detail': 'You already have a restaurant registered.'},
                status=http.HTTP_400_BAD_REQUEST,
            )
        s = PartnerRestaurantSerializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        s.save(owner=request.user, status=Restaurant.Status.PENDING)
        return Response(s.data, status=http.HTTP_201_CREATED)


class PartnerRestaurantView(generics.RetrieveUpdateAPIView):
    """GET / PATCH my restaurant. 404 means this user has not onboarded yet."""

    serializer_class = PartnerRestaurantSerializer

    def get_object(self):
        return partner_restaurant(self.request)


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
