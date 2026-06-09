# orders/serializers.py

from PIL.Image import item
from rest_framework import serializers

from stock.models import StockBatch
from .models import Order, OrderItem
from django.db import transaction
from products.models import Product
from promotions.models import Coupon
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

    # 🔥 ADD THESE (if exist in model)
    razorpay_order_id = serializers.CharField(read_only=True)
    razorpay_payment_id = serializers.CharField(read_only=True)

    # 🚚 If you have address relation
    address = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'total_amount',
            'discount_amount',
            'coupon_code',
            'payment_status',
            'order_status',
            'created_at',
            'items',
            'razorpay_order_id',
            'razorpay_payment_id',
            'address'
        ]

    address = serializers.SerializerMethodField()

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
        coupon_code = validated_data.get('coupon_code')
        address_id = validated_data.get('address_id')
        payment_method = validated_data.get('payment_method')

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

        # ---------------- TOTAL CALC ----------------
        total_amount = 0
        order_items = []

        for item in items_data:
            product = item['product']
            price = product.discounted_price()

            total_amount += price * item['quantity']

            order_items.append({
                "product": product,
                "quantity": item['quantity'],
                "price": price
            })

        # ---------------- COUPON ----------------
        discount_amount = 0
        applied_coupon = None

        if coupon_code:
            try:
                applied_coupon = Coupon.objects.get(code=coupon_code)
                discount_amount = applied_coupon.calculate_discount(total_amount)
                total_amount -= discount_amount
            except Coupon.DoesNotExist:
                raise serializers.ValidationError("Invalid coupon code")

        # ---------------- CREATE ORDER ----------------
        order = Order.objects.create(
            user=user,
            total_amount=total_amount,
            coupon=applied_coupon,
            discount_amount=discount_amount,
            payment_status="PENDING",
            payment_method=payment_method,   # ✅ IMPORTANT FIX
            address_snapshot=address_snapshot
        )

        # ---------------- ORDER ITEMS + STOCK ----------------
        for item in order_items:
            total_price = item['price'] * item['quantity']

            batch = (
            StockBatch.objects
                .filter(product=item['product'], quantity__gte=item['quantity'])
                .order_by('created_at')  # oldest first
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

            # Deduct from batch too
            if batch:
                batch.quantity -= item['quantity']
                batch.save()


            inventory = item['product'].inventory
            inventory.total_stock -= item['quantity']
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
            "amount": str(total_amount),
            "currency": "INR",
            "payment_method": payment_method,
            "payment_status": order.payment_status,
            "order_status": order.order_status
        }