from PIL.Image import item
from rest_framework import serializers

from orders.location_utils import validate_user_location
from stock.models import StockBatch
from .models import Order, OrderItem
from django.db import transaction
from products.models import Product
from promotions.models import Coupon, DeliveryPass, DeliverySettings
import razorpay
from addresses.models import Address


client = razorpay.Client(auth=("rzp_test_StsVgck8iNAA8a", "2950kn0jDNssYM656rGoJAt3"))


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    batch_no = serializers.CharField(source='batch.batch_no', read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product',
            'product_name',
            'quantity',
            'price',
            'total_price',
            'batch',
            'batch_no'
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    coupon_code = serializers.CharField(source='coupon.code', read_only=True)

    razorpay_order_id = serializers.CharField(read_only=True)
    razorpay_payment_id = serializers.CharField(read_only=True)

    address = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'total_amount',
            'discount_amount',
            'delivery_fee',
            'coupon_code',
            'payment_status',
            'order_status',
            'created_at',
            'items',
            'razorpay_order_id',
            'razorpay_payment_id',
            'address'
        ]

    def get_address(self, obj):
        return obj.address_snapshot


class CreateOrderItemSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all()
    )
    quantity = serializers.IntegerField()


class CreateOrderSerializer(serializers.Serializer):
    items = CreateOrderItemSerializer(many=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    address_id = serializers.IntegerField(required=True)
    payment_method = serializers.CharField(required=True)
    current_lat = serializers.FloatField(required=True)
    current_lng = serializers.FloatField(required=True)

    ALLOWED_PINCODES = [
        "741121",
        "741122",
    ]

    def validate(self, data):
        items = data.get('items')

        if not items:
            raise serializers.ValidationError("Order must contain at least one item")

        validated_items = []

        for item in items:
            product = item['product']
            inventory = product.inventory

            if item['quantity'] > inventory.available_stock():
                raise serializers.ValidationError(
                    f"Insufficient stock for {product.name}"
                )

            validated_items.append({
                "product": product,
                "quantity": item['quantity']
            })

        data['items'] = validated_items
        return data

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        items_data = validated_data['items']
        coupon_code = validated_data.get('coupon_code', '').strip().upper()
        address_id = validated_data.get('address_id')
        payment_method = validated_data.get('payment_method')
        current_lat = validated_data.get('current_lat')
        current_lng = validated_data.get('current_lng')

        # ---------------- LOAD SETTINGS FROM DB ----------------
        config = DeliverySettings.get()

        DELIVERY_FEE        = config.delivery_fee        # e.g. ₹40
        MIN_ORDER_DELIVERY  = config.free_delivery_min   # e.g. ₹149
        MIN_ORDER_COUPON    = config.coupon_unlock_min   # e.g. ₹299

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

        if address_snapshot["pincode"] not in self.ALLOWED_PINCODES:
            raise serializers.ValidationError({
                "pincode": "Sorry, delivery is not available in your area."
            })

        # ---------------- LOCATION CHECK ----------------
        location_check = validate_user_location(
            current_lat=current_lat,
            current_lng=current_lng,
            address_pincode=address_snapshot["pincode"]
        )

        if not location_check["valid"]:
            raise serializers.ValidationError({
                "location": location_check["error"]
            })

        # ---------------- TOTAL CALC (subtotal only) ----------------
        subtotal = 0
        order_items = []

        for item in items_data:
            product = item['product']
            price = product.discounted_price()

            subtotal += price * item['quantity']

            order_items.append({
                "product": product,
                "quantity": item['quantity'],
                "price": price
            })

        # ---------------- DELIVERY FEE ----------------
        delivery_fee = DELIVERY_FEE  # default — always charge unless pass qualifies

        delivery_pass = getattr(user, 'delivery_pass', None)
        pass_active = delivery_pass and delivery_pass.is_valid()

        if pass_active:
            if subtotal >= MIN_ORDER_DELIVERY:
                # pass qualifies — check monthly cap
                if delivery_pass.can_use_free_delivery():
                    delivery_fee = 0                    # ✅ free delivery
                    delivery_pass.use_free_delivery()   # increment monthly counter
                else:
                    # cap hit for this month
                    raise serializers.ValidationError(
                        "You've used all 20 free deliveries this month. "
                        "Free deliveries reset on the 1st of next month."
                    )
            # subtotal < MIN_ORDER_DELIVERY → charge normal fee, no error

        # ---------------- COUPON ----------------
        discount_amount = 0
        applied_coupon = None

        if coupon_code:
            # Gate 1 — members only
            if not pass_active:
                raise serializers.ValidationError(
                    "Coupons are available for Pass members only."
                )

            # Gate 2 — subtotal must reach unlock threshold
            if subtotal < MIN_ORDER_COUPON:
                shortage = MIN_ORDER_COUPON - subtotal
                raise serializers.ValidationError(
                    f"Add items worth ₹{shortage:.0f} more to unlock coupons."
                )

            # Gate 3 — coupon exists, active, not expired
            try:
                applied_coupon = Coupon.objects.get(code=coupon_code)
            except Coupon.DoesNotExist:
                raise serializers.ValidationError("Invalid coupon code.")

            if not applied_coupon.is_valid():
                raise serializers.ValidationError(
                    "This coupon has expired or is inactive."
                )

            # Gate 4 — coupon's own min order (against subtotal)
            if subtotal < float(applied_coupon.min_order_amount):
                raise serializers.ValidationError(
                    f"This coupon requires a minimum order of ₹{applied_coupon.min_order_amount}."
                )

            # Gate 5 — one-time use check
            if applied_coupon.one_time_per_user:
                already_used = CouponUsage.objects.filter(
                    coupon=applied_coupon, user=user
                ).exists()
                if already_used:
                    raise serializers.ValidationError(
                        "You have already used this coupon."
                    )

            # ✅ All gates passed — calculate discount on subtotal
            discount_amount = applied_coupon.calculate_discount(float(subtotal))

        # ---------------- FINAL TOTAL ----------------
        # subtotal - coupon discount + delivery fee
        total_amount = subtotal - discount_amount + delivery_fee

        # ---------------- CREATE ORDER ----------------
        order = Order.objects.create(
            user=user,
            total_amount=total_amount,
            coupon=applied_coupon,
            discount_amount=discount_amount,
            delivery_fee=delivery_fee,          # ← store delivery fee on order
            payment_status="PENDING",
            payment_method=payment_method,
            address_snapshot=address_snapshot
        )

        # ---------------- ORDER ITEMS + STOCK ----------------
        for item in order_items:
            total_price = item['price'] * item['quantity']

            batch = (
                StockBatch.objects
                .filter(product=item['product'], quantity__gte=item['quantity'])
                .order_by('created_at')   # oldest first (FIFO)
                .first()
            )

            OrderItem.objects.create(
                order=order,
                product=item['product'],
                quantity=item['quantity'],
                price=item['price'],
                total_price=total_price,
                batch=batch,
            )

            # Deduct from batch
            if batch:
                batch.quantity -= item['quantity']
                batch.save()

            # Deduct from inventory
            inventory = item['product'].inventory

            if inventory.total_stock < item['quantity']:
                raise serializers.ValidationError(
                    f"Insufficient stock for {item['product'].name}"
                )

            inventory.total_stock -= item['quantity']

            if inventory.reserved_stock >= item['quantity']:
                inventory.reserved_stock -= item['quantity']
            else:
                inventory.reserved_stock = 0

            inventory.save()

        # ---------------- PAYMENT FLOW ----------------
        razorpay_order_id = None

        if payment_method == "RAZORPAY":
            razorpay_order = client.order.create({
                "amount": int(total_amount * 100),
                "currency": "INR",
                "payment_capture": 1
            })

            razorpay_order_id = razorpay_order["id"]
            order.razorpay_order_id = razorpay_order_id
            order.save()

        elif payment_method == "COD":
            order.payment_status = "PENDING"
            order.save()

        # ---------------- RESPONSE ----------------
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
        }