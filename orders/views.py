# orders/views.py

from rest_framework.generics import ListAPIView, RetrieveAPIView, CreateAPIView
from rest_framework.permissions import IsAuthenticated
from .models import Order
from .serializers import OrderSerializer, CreateOrderSerializer, ValidateOrderSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import hmac
import hashlib
from django.conf import settings
from orders.models import Order, DeliveryAssignment
from orders.services.driver_assignment import User, assign_driver
from django.core.cache import cache
from django.core.mail import send_mail
import random
from orders.utils import notify_driver
from promotions.models import Coupon, CouponUsage
from datetime import date, timedelta              # 👈 add
from orders.slot_utils import generate_slots      # 👈 add
from rest_framework.decorators import api_view, permission_classes  # 👈 add


class OrderListView(ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.is_staff or getattr(user, "role", None) == "ADMIN":
            return Order.objects.all().prefetch_related('items__product').order_by('-id')

        elif getattr(user, "role", None) == "DRIVER":
            return Order.objects.filter(driver=user).prefetch_related('items__product').order_by('-id')

        return Order.objects.filter(user=user).prefetch_related('items__product').order_by('-id')


class OrderDetailView(RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.is_staff or getattr(user, "role", None) == "ADMIN":
            return Order.objects.all()

        elif getattr(user, "role", None) == "DRIVER":
            return Order.objects.filter(driver=user)

        return Order.objects.filter(user=user)


class CancelOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            order = Order.objects.get(id=pk, user=request.user)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if order.order_status == "DELIVERED":
            return Response({"error": "Delivered order cannot be cancelled"}, status=400)

        if order.order_status == "CANCELLED":
            return Response({"error": "Order already cancelled"}, status=400)

        order.mark_cancelled()

        return Response({"message": "Order cancelled successfully"})


class UpdateOrderStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if not (user.is_staff or getattr(user, "role", None) in ["ADMIN", "DELIVERY"]):
            return Response({"error": "Permission denied"}, status=403)

        status_value = request.data.get("status")

        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if status_value == "SHIPPED":
            order.mark_shipped()
        elif status_value == "DELIVERED":
            order.mark_delivered()
        elif status_value == "CONFIRMED":
            order.order_status = "CONFIRMED"
            order.save()
        else:
            return Response({"error": "Invalid status"}, status=400)

        return Response({"message": "Order status updated"})


class CreateOrderView(CreateAPIView):
    serializer_class = CreateOrderSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)
        data = serializer.save()

        try:
            order_id = data.get('order_id') or data.get('id')
            order = Order.objects.get(id=order_id)

            existing = DeliveryAssignment.objects.filter(order=order).first()
            if not existing:
                driver = assign_driver(order)
                if driver:
                    assignment = DeliveryAssignment.objects.create(
                        order=order,
                        driver=driver,
                        status="ASSIGNED"
                    )
                    notify_driver(driver.id, {
                        "order_id": order.id,
                        "order_status": order.order_status,
                        "payment_status": order.payment_status,
                        "total_amount": float(order.total_amount),
                        "customer_name": order.user.first_name+" "+order.user.middle_name+" "+order.user.last_name,
                        "customer_phone": order.user.phone,
                        "address": order.address_snapshot,
                        "assigned_at": str(assignment.assigned_at),
                        "status": assignment.status,
                    })
                    print(f'📤 Auto assigned driver {driver.id} to order {order.id}')
        except Exception as e:
            print(f'⚠️ Auto assign failed: {e}')

        try:
            coupon_code = request.data.get("coupon_code", "").strip().upper()
            if coupon_code:
                coupon = Coupon.objects.get(code=coupon_code, one_time_per_user=True)
                CouponUsage.objects.get_or_create(coupon=coupon, user=request.user)
        except Coupon.DoesNotExist:
            pass
        except Exception as e:
            print(f'⚠️ Coupon usage recording failed: {e}')

        return Response(data, status=201)


class VerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payment_id = request.data.get("razorpay_payment_id")
        order_id = request.data.get("razorpay_order_id")
        signature = request.data.get("razorpay_signature")

        try:
            order = Order.objects.get(razorpay_order_id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        generated_signature = hmac.new(
            key=settings.RAZORPAY_SECRET.encode(),
            msg=f"{order_id}|{payment_id}".encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        if generated_signature == signature:
            order.razorpay_payment_id = payment_id
            order.razorpay_signature = signature
            order.mark_paid()
            return Response({"status": "Payment Verified & Order Updated"})
        else:
            order.mark_failed()
            return Response({"status": "Invalid Payment"}, status=400)


class AssignDriverView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not request.user.is_staff:
            return Response({"error": "Only admin can assign driver"}, status=403)

        driver_id = request.data.get("driver_id")

        try:
            order = Order.objects.get(id=pk)
            driver = User.objects.get(id=driver_id)
            order.driver = driver
            order.save()
            return Response({"message": "Driver assigned"})
        except:
            return Response({"error": "Invalid data"}, status=400)


class AutoAssignDriverAPIView(APIView):

    def post(self, request):
        order_id = request.data.get("order_id")

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        existing = DeliveryAssignment.objects.filter(order=order).first()
        if existing:
            notify_driver(existing.driver.id, {
                "order_id": order.id,
                "order_status": order.order_status,
                "payment_status": order.payment_status,
                "total_amount": float(order.total_amount),
                "customer_name": order.user.first_name+" "+order.user.middle_name+" "+order.user.last_name,
                "customer_phone": order.user.phone,
                "address": order.address_snapshot,
                "assigned_at": str(existing.assigned_at),
                "status": existing.status,
            })
            return Response({
                "message": "Driver already assigned — notified again",
                "driver_id": existing.driver.id,
                "assignment_id": existing.id
            })

        driver = assign_driver(order)
        if not driver:
            return Response({"error": "No driver available"}, status=404)

        assignment = DeliveryAssignment.objects.create(
            order=order,
            driver=driver,
            status="ASSIGNED"
        )

        notify_driver(driver.id, {
            "order_id": order.id,
            "order_status": order.order_status,
            "payment_status": order.payment_status,
            "total_amount": float(order.total_amount),
            "customer_name": order.user.first_name+" "+order.user.middle_name+" "+order.user.last_name,
            "customer_phone": order.user.phone,
            "address": order.address_snapshot,
            "assigned_at": str(assignment.assigned_at),
            "status": assignment.status,
        })

        return Response({
            "message": "Driver assigned",
            "driver_id": driver.id,
            "assignment_id": assignment.id
        })


class DriverAssignedOrdersAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != "DELIVERY":
            return Response({"error": "Not a driver"}, status=403)

        assignments = DeliveryAssignment.objects.filter(
            driver=user
        ).select_related("order", "order__user").order_by("-assigned_at")

        data = []

        for a in assignments:
            order = a.order
            customer = order.user

            data.append({
                "assignment_id": a.id,
                "order_id": order.id,
                "order_status": order.order_status,
                "payment_status": order.payment_status,
                "total_amount": order.total_amount,
                "customer_name": customer.username,
                "customer_phone": customer.phone,
                "customer_email": customer.email,
                "address": order.address_snapshot if order.address_snapshot else customer.address,
                "assigned_at": a.assigned_at,
                "status": a.status,
            })

        return Response(data)


class ConfirmPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        if getattr(user, "role", None) not in ["DELIVERY", "ADMIN"] and not user.is_staff:
            return Response({"error": "Permission denied"}, status=403)

        if not getattr(user, "is_online", False) and not user.is_staff:
            return Response(
                {"error": "You must be ONLINE to confirm payment"},
                status=403
            )

        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        payment_method = request.data.get("payment_method", "").upper()
        status_value   = request.data.get("status", "").upper()

        if status_value != "PAID":
            return Response({"error": "Invalid status value"}, status=400)

        if payment_method not in ["COD", "UPI"]:
            return Response({"error": "Invalid payment method"}, status=400)

        if order.payment_status == "PAID":
            return Response({"message": "Payment already confirmed"})

        order.payment_status = "PAID"
        order.payment_method = payment_method
        order.save()

        return Response({
            "message": f"{payment_method} payment confirmed successfully"
        }, status=200)


class SendDeliveryOtpAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        if getattr(user, "role", None) not in ["DELIVERY", "ADMIN"] and not user.is_staff:
            return Response({"error": "Permission denied"}, status=403)

        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        assignment = DeliveryAssignment.objects.filter(
            order=order, driver=user
        ).first()

        if not assignment:
            return Response(
                {"error": "You are not assigned to this order"},
                status=403
            )

        otp = str(random.randint(100000, 999999))
        cache.set(f"delivery_otp:{pk}", otp, timeout=600)

        customer_email = order.user.email
        customer_name  = order.user.username

        try:
            send_mail(
                subject="Your Delivery OTP",
                message=(
                    f"Hi {customer_name},\n\n"
                    f"Your delivery OTP for Order #{pk} is: {otp}\n\n"
                    f"Please share this with the delivery driver to complete your order.\n\n"
                    f"Do not share this with anyone else."
                ),
                from_email="no-reply@yourapp.com",
                recipient_list=[customer_email],
            )
        except Exception as e:
            cache.delete(f"delivery_otp:{pk}")
            return Response(
                {"error": f"Failed to send OTP email: {str(e)}"},
                status=500
            )

        return Response({
            "message": f"OTP sent to customer email ({customer_email})"
        }, status=200)


class VerifyDeliveryOtpAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        if getattr(user, "role", None) not in ["DELIVERY", "ADMIN"] and not user.is_staff:
            return Response({"error": "Permission denied"}, status=403)

        otp_input = request.data.get("otp")

        if not otp_input:
            return Response({"error": "OTP is required"}, status=400)

        cached_otp = cache.get(f"delivery_otp:{pk}")

        if not cached_otp:
            return Response({"error": "OTP expired or not sent yet"}, status=400)

        if str(cached_otp) != str(otp_input):
            return Response({"error": "Invalid OTP"}, status=400)

        cache.delete(f"delivery_otp:{pk}")

        return Response({"message": "OTP verified successfully"}, status=200)


class ValidateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ValidateOrderSerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            return Response({"valid": True}, status=200)

        return Response(serializer.errors, status=400)


# 👇 NEW — delivery slots view
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_delivery_slots(request):
    """
    Returns available 30-min slots for the next 7 days.
    GET /api/orders/slots/
    """
    slots_by_date = []
    today = date.today()

    for i in range(7):
        target_date = today + timedelta(days=i)
        slots_by_date.append({
            "date":     target_date.isoformat(),
            "day":      target_date.strftime("%A"),
            "is_today": target_date == today,
            "slots":    generate_slots(target_date),
        })

    return Response(slots_by_date)