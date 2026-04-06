# orders/serializers.py

from rest_framework import serializers
from .models import Order, OrderItem
from django.db import transaction
from products.models import Product
from promotions.models import Coupon

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product',
            'product_name',
            'quantity',
            'price',
            'total_price'
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    coupon_code = serializers.CharField(source='coupon.code', read_only=True)

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
            'items'
        ]


class CreateOrderItemSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
    queryset=Product.objects.all()
    )
    quantity = serializers.IntegerField()


class CreateOrderSerializer(serializers.Serializer):
    items = CreateOrderItemSerializer(many=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        items = data.get('items')

        if not items:
            raise serializers.ValidationError("Order must contain at least one item")

        validated_items = []

        for item in items:
            try:
                product=item['product']
            except Product.DoesNotExist:
                raise serializers.ValidationError(f"Product {item['product']} not found")

            inventory = product.inventory
            if item['quantity'] > inventory.available_stock():
                raise serializers.ValidationError(
                    f"Insufficient stock for {product.name}"
                )

            # ✅ Store product OBJECT (important)
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

        total_amount = 0
        order_items = []

        # ✅ NO Product.objects.get here anymore
        for item in items_data:
            product = item['product']  # already object
            price = product.discounted_price()

            total_amount += price * item['quantity']

            order_items.append({
                "product": product,
                "quantity": item['quantity'],
                "price": price
            })

        discount_amount = 0
        applied_coupon = None

        # Apply coupon
        if coupon_code:
            try:
                applied_coupon = Coupon.objects.get(code=coupon_code)
                discount_amount = applied_coupon.calculate_discount(total_amount)
                total_amount -= discount_amount
            except Coupon.DoesNotExist:
                raise serializers.ValidationError("Invalid coupon code")

        # Create Order
        order = Order.objects.create(
            user=user,
            total_amount=total_amount,
            coupon=applied_coupon,
            discount_amount=discount_amount
        )

        # ✅ Create Order Items + Update Inventory
        for item in order_items:
            total_price = item['price'] * item['quantity']   # ✅ DEFINE FIRST

            OrderItem.objects.create(
                order=order,
                product=item['product'],
                quantity=item['quantity'],
                price=item['price'],
                total_price=total_price   # ✅ now works
            )

            inventory = item['product'].inventory
            inventory.total_stock -= item['quantity']

            if inventory.reserved_stock >= item['quantity']:
                inventory.reserved_stock -= item['quantity']

            inventory.save()
            return order