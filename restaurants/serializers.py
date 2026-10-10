from rest_framework import serializers

from .models import (
    Cuisine,
    MenuCategory,
    MenuItem,
    Restaurant,
    RestaurantOrder,
    RestaurantOrderItem,
)
from .utils import fmt_time


def absolute_url(request, file_field):
    if not file_field:
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


class CuisineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cuisine
        fields = ['id', 'name']


# --------------------------------------------------------------- customer: restaurants
class RestaurantListSerializer(serializers.ModelSerializer):
    """Keys match Restaurant.fromJson in the Flutter app."""

    cuisines = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    rating = serializers.FloatField(read_only=True)
    delivery_fee = serializers.FloatField(read_only=True)
    distance_km = serializers.SerializerMethodField()
    eta_min = serializers.SerializerMethodField()
    eta_max = serializers.SerializerMethodField()
    is_open = serializers.BooleanField(source='is_open_now', read_only=True)
    opens_at = serializers.SerializerMethodField()
    closes_at = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            'id', 'name', 'cuisines', 'image', 'rating', 'rating_count',
            'eta_min', 'eta_max', 'distance_km', 'is_open', 'opens_at', 'closes_at',
            'offer_percent', 'offer_max_discount', 'offer_code', 'delivery_fee',
        ]

    def get_cuisines(self, obj):
        return [c.name for c in obj.cuisines.all()]

    def get_image(self, obj):
        return absolute_url(self.context.get('request'), obj.cover_image or obj.logo)

    def _distance(self, obj):
        return obj.distance_from(self.context.get('lat'), self.context.get('lng'))

    def get_distance_km(self, obj):
        d = self._distance(obj)
        return None if d is None else round(d, 1)

    def get_eta_min(self, obj):
        return obj.eta_range(self._distance(obj))[0]

    def get_eta_max(self, obj):
        return obj.eta_range(self._distance(obj))[1]

    def get_opens_at(self, obj):
        return fmt_time(obj.opens_at)

    def get_closes_at(self, obj):
        return fmt_time(obj.closes_at)


class RestaurantDetailSerializer(RestaurantListSerializer):
    logo = serializers.SerializerMethodField()
    min_order_amount = serializers.FloatField(read_only=True)
    offer_min_order = serializers.FloatField(read_only=True)

    class Meta(RestaurantListSerializer.Meta):
        fields = RestaurantListSerializer.Meta.fields + [
            'description', 'address_line', 'city', 'logo', 'min_order_amount', 'offer_min_order',
        ]

    def get_logo(self, obj):
        return absolute_url(self.context.get('request'), obj.logo)


class MenuItemSerializer(serializers.ModelSerializer):
    """Keys match MenuItem.fromJson in the Flutter app."""

    restaurant = serializers.IntegerField(source='restaurant_id', read_only=True)
    category = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            'id', 'restaurant', 'name', 'description', 'category', 'is_veg', 'price', 'mrp',
            'image', 'is_available', 'packaging_charge', 'discount_percent',
        ]

    def get_category(self, obj):
        return obj.category.name if obj.category else 'Recommended'

    def get_image(self, obj):
        return absolute_url(self.context.get('request'), obj.image)


# --------------------------------------------------------------- customer: orders
class OrderLineInputSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=20)


class QuoteSerializer(serializers.Serializer):
    restaurant_id = serializers.IntegerField()
    items = OrderLineInputSerializer(many=True, allow_empty=False)
    address_id = serializers.IntegerField(required=False)


class PlaceOrderSerializer(QuoteSerializer):
    address_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(choices=RestaurantOrder.PaymentMethod.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=300)


class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RestaurantOrder.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantOrderItem
        fields = ['id', 'menu_item', 'name', 'is_veg', 'unit_price', 'quantity', 'line_total']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    restaurant = serializers.SerializerMethodField()
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_label = serializers.CharField(source='get_payment_method_display', read_only=True)
    payment_status_label = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = RestaurantOrder
        fields = [
            'id', 'order_number', 'status', 'status_label', 'payment_method',
            'payment_method_label', 'payment_status', 'payment_status_label', 'restaurant',
            'items', 'item_total', 'discount', 'delivery_fee', 'packaging_charge', 'gst',
            'total_amount', 'offer_code', 'customer_name', 'customer_phone',
            'delivery_address', 'delivery_lat', 'delivery_lng', 'notes', 'rejection_reason',
            'razorpay_order_id', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_restaurant(self, obj):
        r = obj.restaurant
        return {
            'id': r.id,
            'name': r.name,
            'phone': r.phone,
            'image': absolute_url(self.context.get('request'), r.cover_image or r.logo),
        }


# --------------------------------------------------------------- partner (restaurant owner)
class PartnerRestaurantSerializer(serializers.ModelSerializer):
    cuisines = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Cuisine.objects.all(), required=False
    )
    cuisine_names = serializers.SerializerMethodField()
    is_open_now = serializers.BooleanField(read_only=True)
    # Multipart forms drop unticked booleans to False; default=True keeps the model default.
    is_accepting_orders = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Restaurant
        fields = [
            'id', 'name', 'description', 'cuisines', 'cuisine_names', 'phone', 'email',
            'address_line', 'city', 'pincode', 'latitude', 'longitude', 'fssai_number',
            'logo', 'cover_image', 'opens_at', 'closes_at', 'is_accepting_orders',
            'avg_prep_minutes', 'min_order_amount', 'offer_percent', 'offer_max_discount',
            'offer_min_order', 'offer_code',
            # read only for the restaurant
            'status', 'rejection_reason', 'rating', 'rating_count', 'delivery_fee',
            'delivery_radius_km', 'is_open_now',
        ]
        read_only_fields = [
            'status', 'rejection_reason', 'rating', 'rating_count', 'delivery_fee',
            'delivery_radius_km',
        ]
        extra_kwargs = {'fssai_number': {'required': True, 'allow_blank': False}}

    def get_cuisine_names(self, obj):
        return [c.name for c in obj.cuisines.all()]


class MenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = ['id', 'name', 'sort_order']

    def validate_name(self, value):
        restaurant = self.context['restaurant']
        qs = MenuCategory.objects.filter(restaurant=restaurant, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('You already have a category with this name.')
        return value


class AdminMenuCategorySerializer(serializers.ModelSerializer):
    restaurant = serializers.PrimaryKeyRelatedField(queryset=Restaurant.objects.all())
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    class Meta:
        model = MenuCategory
        fields = ['id', 'restaurant', 'restaurant_name', 'name', 'sort_order']

    def validate(self, attrs):
        restaurant = attrs.get('restaurant', getattr(self.instance, 'restaurant', None))
        name = attrs.get('name', getattr(self.instance, 'name', None))
        queryset = MenuCategory.objects.filter(restaurant=restaurant, name__iexact=name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                {'name': 'This restaurant already has a category with this name.'}
            )
        return attrs


class PartnerMenuItemSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=MenuCategory.objects.none(), required=False, allow_null=True
    )
    category_name = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField(read_only=True)
    # Multipart forms (dish photo upload) drop missing booleans to False; keep the defaults.
    is_veg = serializers.BooleanField(required=False, default=True)
    is_available = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = MenuItem
        fields = [
            'id', 'name', 'description', 'category', 'category_name', 'is_veg', 'price', 'mrp',
            'discount_percent', 'image', 'is_available', 'packaging_charge', 'sort_order',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        restaurant = self.context.get('restaurant')
        if restaurant is not None:
            self.fields['category'].queryset = MenuCategory.objects.filter(restaurant=restaurant)

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def validate(self, attrs):
        price = attrs.get('price', getattr(self.instance, 'price', None))
        mrp = attrs.get('mrp', getattr(self.instance, 'mrp', None))
        if mrp is not None and price is not None and mrp < price:
            raise serializers.ValidationError({'mrp': 'MRP cannot be lower than the selling price.'})
        return attrs


# --------------------------------------------------------------- admin (Instant team)
class AdminRestaurantSerializer(serializers.ModelSerializer):
    cuisines = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Cuisine.objects.all(), required=False
    )
    owner_name = serializers.SerializerMethodField()
    is_open_now = serializers.BooleanField(read_only=True)
    is_accepting_orders = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Restaurant
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def get_owner_name(self, obj):
        return obj.owner.get_full_name() or str(obj.owner)
