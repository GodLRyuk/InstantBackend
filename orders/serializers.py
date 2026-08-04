from PIL.Image import item
from rest_framework import serializers

from orders.location_utils import validate_user_location, calculate_delivery_fee, ALLOWED_PINCODES  # ✅ CHANGED
from stock.models import StockBatch
from .models import CashRemittance, CashRemittanceItem, CashRemittanceItem, Order, OrderItem
from django.db import transaction
from products.models import Product
from promotions.models import Coupon, CouponUsage, DeliveryPass
from promotions.models import DeliverySettings
import razorpay
from addresses.models import Address
from datetime import date as date_type
from django.conf import settings as django_settings
from decimal import Decimal

client = razorpay.Client(auth=(django_settings.RAZORPAY_KEY_ID, django_settings.RAZORPAY_SECRET))


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    batch_no = serializers.CharField(source='batch.batch_no', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'total_price', 'batch', 'batch_no']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    coupon_code = serializers.CharField(source='coupon.code', read_only=True)
    razorpay_order_id = serializers.CharField(read_only=True)
    razorpay_payment_id = serializers.CharField(read_only=True)
    address = serializers.SerializerMethodField()
    driver_id = serializers.SerializerMethodField()

    def get_driver_id(self, obj):
        from orders.models import DeliveryAssignment
        assignment = DeliveryAssignment.objects.filter(order=obj).order_by('-assigned_at').first()
        return assignment.driver_id if assignment else None

    class Meta:
        model = Order
        fields = [
            'id', 'total_amount', 'discount_amount', 'delivery_fee', 'coupon_code',
            'payment_status', 'order_status', 'created_at', 'items',
            'razorpay_order_id', 'razorpay_payment_id', 'address',
            'delivery_type', 'scheduled_date', 'scheduled_slot_start',
            'scheduled_slot_end', 'driver_id',
        ]

    def get_address(self, obj):
        return obj.address_snapshot


class CreateOrderItemSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField()


class CreateOrderSerializer(serializers.Serializer):
    items = CreateOrderItemSerializer(many=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    address_id = serializers.IntegerField(required=True)
    payment_method = serializers.CharField(required=True)

    current_lng = serializers.FloatField(required=False, allow_null=True)  
    delivery_type        = serializers.ChoiceField(choices=["ASAP", "SCHEDULED"], default="ASAP")
    scheduled_date       = serializers.DateField(required=False, allow_null=True)
    scheduled_slot_start = serializers.TimeField(required=False, allow_null=True)
    scheduled_slot_end   = serializers.TimeField(required=False, allow_null=True)

    def validate(self, data):
        items = data.get('items')
        if not items:
            raise serializers.ValidationError("Order must contain at least one item")

        validated_items = []
        for item in items:
            product = item['product']
            inventory = product.inventory
            if item['quantity'] > inventory.available_stock():
                raise serializers.ValidationError(f"Insufficient stock for {product.name}")
            validated_items.append({"product": product, "quantity": item['quantity']})

        data['items'] = validated_items

        if data.get("delivery_type") == "SCHEDULED":
            if not data.get("scheduled_date"):
                raise serializers.ValidationError("scheduled_date is required for scheduled delivery.")
            if not data.get("scheduled_slot_start"):
                raise serializers.ValidationError("scheduled_slot_start is required for scheduled delivery.")
            if not data.get("scheduled_slot_end"):
                raise serializers.ValidationError("scheduled_slot_end is required for scheduled delivery.")
            if data["scheduled_date"] < date_type.today():
                raise serializers.ValidationError("scheduled_date cannot be in the past.")

        return data

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        items_data = validated_data['items']
        coupon_code = validated_data.get('coupon_code', '').strip().upper()
        address_id = validated_data.get('address_id')
        payment_method = validated_data.get('payment_method')
        current_lat = validated_data.get('current_lat')   # kept — still useful for driver nav/fraud signal
        current_lng = validated_data.get('current_lng')

        delivery_type        = validated_data.get('delivery_type', 'ASAP')
        scheduled_date       = validated_data.get('scheduled_date')
        scheduled_slot_start = validated_data.get('scheduled_slot_start')
        scheduled_slot_end   = validated_data.get('scheduled_slot_end')

        config = DeliverySettings.get()
        MIN_ORDER_DELIVERY  = config.free_delivery_min
        MIN_ORDER_COUPON    = config.coupon_unlock_min

        # ---------------- ADDRESS ----------------
        try:
            address = Address.objects.get(id=address_id, user=user)
        except Address.DoesNotExist:
            raise serializers.ValidationError("Invalid address selected")

        address_snapshot = {
            "full_address": address.full_address,
            "name": address.name,
            "phone": address.phone,
            "city": address.city,
            "state": address.state,
            "pincode": str(address.pincode).strip(),
            "address_type": address.address_type,
        }

        if address_snapshot["pincode"] not in ALLOWED_PINCODES:
            raise serializers.ValidationError({"pincode": "Sorry, delivery is not available in your area."})

        # ---------------- LOCATION CHECK (address-pincode based) ----------------
        # ✅ CHANGED — no longer passes current_lat/current_lng
        location_check = validate_user_location(address)

        if not location_check["valid"]:
            raise serializers.ValidationError({"location": location_check["error"]})

        # ---------------- TOTAL CALC ----------------
        subtotal = Decimal("0.00")
        order_items = []
        for item in items_data:
            product = item['product']
            price = product.discounted_price()
            subtotal += price * item['quantity']
            order_items.append({"product": product, "quantity": item['quantity'], "price": price})

        # ---------------- DELIVERY FEE — distance-based ----------------
        # ✅ CHANGED — was: delivery_fee = config.delivery_fee (flat)
        delivery_fee = Decimal(str(calculate_delivery_fee(
        distance_km=location_check["distance_km"],
        base_fee=config.base_delivery_fee,
        base_km=config.base_delivery_km,
        per_km_charge=config.per_km_charge,
        )))

        delivery_pass = getattr(user, 'delivery_pass', None)
        pass_active = delivery_pass and delivery_pass.is_valid()

        if pass_active:
            if subtotal >= MIN_ORDER_DELIVERY:
                if delivery_pass.can_use_free_delivery():
                    delivery_fee = Decimal("0.00")
                    delivery_pass.use_free_delivery()
                else:
                    raise serializers.ValidationError(
                        "You've used all 20 free deliveries this month. "
                        "Free deliveries reset on the 1st of next month."
                    )

        # ---------------- COUPON ----------------
        discount_amount = 0
        applied_coupon = None
        if coupon_code:
            if not pass_active:
                raise serializers.ValidationError("Coupons are available for Pass members only.")
            if subtotal < MIN_ORDER_COUPON:
                shortage = MIN_ORDER_COUPON - subtotal
                raise serializers.ValidationError(f"Add items worth ₹{shortage:.0f} more to unlock coupons.")
            try:
                applied_coupon = Coupon.objects.get(code=coupon_code)
            except Coupon.DoesNotExist:
                raise serializers.ValidationError("Invalid coupon code.")
            if not applied_coupon.is_valid():
                raise serializers.ValidationError("This coupon has expired or is inactive.")
            if subtotal < float(applied_coupon.min_order_amount):
                raise serializers.ValidationError(f"This coupon requires a minimum order of ₹{applied_coupon.min_order_amount}.")
            if applied_coupon.one_time_per_user:
                already_used = CouponUsage.objects.filter(coupon=applied_coupon, user=user).exists()
                if already_used:
                    raise serializers.ValidationError("You have already used this coupon.")
            discount_amount = applied_coupon.calculate_discount(subtotal)

        total_amount = subtotal - discount_amount + delivery_fee

        order = Order.objects.create(
            user=user,
            total_amount=total_amount,
            coupon=applied_coupon,
            discount_amount=discount_amount,
            delivery_fee=delivery_fee,
            payment_status="PENDING",
            payment_method=payment_method,
            address_snapshot=address_snapshot,
            delivery_type=delivery_type,
            scheduled_date=scheduled_date,
            scheduled_slot_start=scheduled_slot_start,
            scheduled_slot_end=scheduled_slot_end,
        )

        for item in order_items:
            total_price = item['price'] * item['quantity']
            batch = (
                StockBatch.objects
                .filter(product=item['product'], quantity__gte=item['quantity'])
                .order_by('created_at')
                .first()
            )
            OrderItem.objects.create(
                order=order, product=item['product'], quantity=item['quantity'],
                price=item['price'], total_price=total_price, batch=batch,
            )
            if batch:
                batch.quantity -= item['quantity']
                batch.save()

            inventory = item['product'].inventory
            if inventory.total_stock < item['quantity']:
                raise serializers.ValidationError(f"Insufficient stock for {item['product'].name}")
            inventory.total_stock -= item['quantity']
            if inventory.reserved_stock >= item['quantity']:
                inventory.reserved_stock -= item['quantity']
            else:
                inventory.reserved_stock = 0
            inventory.save()

        razorpay_order_id = None
        if payment_method == "RAZORPAY":
            razorpay_order = client.order.create({
                "amount": int(total_amount * 100), "currency": "INR", "payment_capture": 1
            })
            razorpay_order_id = razorpay_order["id"]
            order.razorpay_order_id = razorpay_order_id
            order.save()
        elif payment_method == "COD":
            order.payment_status = "PENDING"
            order.save()

        return {
            "order_id": order.id,
            "razorpay_order_id": razorpay_order_id,
            "subtotal": str(subtotal),
            "delivery_fee": str(delivery_fee),
            "discount_amount": str(discount_amount),
            "amount": str(total_amount),
            "currency": "INR",
            "payment_method": payment_method,
            "payment_status": order.payment_status,
            "order_status": order.order_status,
            "pass_used": pass_active and delivery_fee == 0,
            "coupon_applied": applied_coupon.code if applied_coupon else None,
            "delivery_type": delivery_type,
            "scheduled_date": str(scheduled_date) if scheduled_date else None,
            "scheduled_slot": f"{scheduled_slot_start}–{scheduled_slot_end}" if scheduled_slot_start else None,
            "distance_km": location_check["distance_km"],   # ✅ NEW — useful for frontend display
        }


class ValidateOrderSerializer(serializers.Serializer):
    items = CreateOrderItemSerializer(many=True)
    address_id = serializers.IntegerField(required=True)
    current_lat = serializers.FloatField(required=False, allow_null=True)
    current_lng = serializers.FloatField(required=False, allow_null=True) 

    def validate(self, data):
        user = self.context['request'].user
        items = data.get('items', [])
        address_id = data.get('address_id')

        try:
            address = Address.objects.get(id=address_id, user=user)
        except Address.DoesNotExist:
            raise serializers.ValidationError({"address": "Invalid address selected"})

        pincode = str(address.pincode).strip()

        if pincode not in ALLOWED_PINCODES:
            raise serializers.ValidationError({"pincode": "Sorry, delivery is not available in your area."})

        # ✅ CHANGED — no longer passes current_lat/current_lng
        location_check = validate_user_location(address) 
        if not location_check["valid"]:
            raise serializers.ValidationError(location_check["error"])

        for item in items:
            product = item['product']
            inventory = product.inventory
            if item['quantity'] > inventory.available_stock():
                raise serializers.ValidationError({"stock": f"Insufficient stock for {product.name}"})

        data['_location_check'] = location_check   # ✅ NEW — stash for the view to read
        return data
class CashRemittanceItemSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id')
    total_amount = serializers.DecimalField(source='order.total_amount', max_digits=10, decimal_places=2)

    class Meta:
        model = CashRemittanceItem
        fields = ['order_id', 'total_amount']


class CashRemittanceSerializer(serializers.ModelSerializer):
    items = CashRemittanceItemSerializer(many=True, read_only=True)
    driver_name = serializers.CharField(source='driver.username', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.username', read_only=True)

    class Meta:
        model = CashRemittance
        fields = [
            'id', 'driver', 'driver_name', 'total_amount', 'amount_received',
            'status', 'recorded_by', 'recorded_by_name', 'recorded_at', 'notes', 'items'
        ]
        read_only_fields = ['status', 'recorded_by', 'recorded_at']

