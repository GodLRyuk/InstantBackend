from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, get_user_model
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from .utils.email_utils import send_otp_email
import random
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.mail import send_mail
from orders.models import Order, DeliveryAssignment
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes


User = get_user_model()


class AdminLoginAPIView(APIView):
    permission_classes = [AllowAny] 
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=email, password=password)

        if user is None:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_staff:
            return Response({'error': 'Not an admin user'}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user_id': user.id,
            'email': user.email,
            'zip_code': user.zip_code,
            'is_staff': user.is_staff,
            'profile_image': request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
        })
class CustomerLoginAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):

        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, username=email, password=password)

        if user is None:
            return Response({"error": "Invalid credentials"}, status=401)

        if user.role != "CUSTOMER":
            return Response({"error": "Not a customer account"}, status=403)

        refresh = RefreshToken.for_user(user)

        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user_id": user.id,
            "email": user.email,
            'phone': user.phone,
            'address': user.address,
            'zip_code': user.zip_code,
            "role": user.role,
            "profile_image": request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
        })

class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        username = request.data.get("username")
        email = request.data.get("email")
        password = request.data.get("password")
        phone = request.data.get("phone")
        address = request.data.get("address")
        zip_code = request.data.get("zip_code")
        role = request.data.get("role", "CUSTOMER")

        profile_image = request.FILES.get("profile_image")

        # ✅ Validation
        if not username or not email or not password or not phone:
            return Response(
                {"error": "username, email, password and phone are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already exists"}, status=400)

        if User.objects.filter(phone=phone).exists():
            return Response({"error": "Phone already exists"}, status=400)

        # ✅ Create user
        if role == "ADMIN":
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                phone=phone,
                address=address,
                zip_code=zip_code,
                role=role,
                is_staff=True,
                is_active=True
            )
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                phone=phone,
                address=address,
                zip_code=zip_code,
                role=role,
                is_active=True
            )

        # ✅ Save profile image
        if profile_image:
            user.profile_image = profile_image
            user.save()

        # 🔐 GENERATE OTP
        otp = str(random.randint(100000, 999999))

        user.otp = otp
        user.otp_created_at = timezone.now()
        user.is_verified = False
        user.otp_attempts = 0
        user.save()

        # 📧 SEND EMAIL OTP
        try:
            send_otp_email(user.email, otp)
        except Exception as e:
            return Response({
                "error": "User created but OTP email failed",
                "details": str(e)
            }, status=500)

        return Response({
            "message": "OTP sent to your email",
            "email": user.email
        }, status=status.HTTP_201_CREATED)

class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "address": user.address,
            "zip_code": user.zip_code,
            "role": user.role,
            "profile_image": request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
        }

        return Response(data, status=status.HTTP_200_OK)
class VerifyOTPAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        otp = request.data.get("otp")
        otp_type = request.data.get("type")

        if otp_type == "register":
            email = request.data.get("email")

            cached_otp = cache.get(f"otp:register:{email}")

            if not cached_otp:
                return Response({"error": "OTP expired"}, status=400)

            if str(cached_otp) != str(otp):
                return Response({"error": "Invalid OTP"}, status=400)

            return Response({"message": "Register OTP verified"}, status=200)

        elif otp_type == "email_change":
            user = request.user

            cached_otp = cache.get(f"otp:email_change:{user.id}")

            if not cached_otp:
                return Response({"error": "OTP expired"}, status=400)

            if str(cached_otp) != str(otp):
                return Response({"error": "Invalid OTP"}, status=400)

            return Response({"message": "OTP verified successfully"}, status=200)

        return Response({"error": "Invalid OTP type"}, status=400)
class ResendOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response({"error": "Email required"}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        # 🔥 generate new OTP
        otp = str(random.randint(100000, 999999))

        user.otp = otp
        user.otp_created_at = timezone.now()
        user.otp_attempts = 0
        user.save()

        # 📧 send email (if you already implemented)
        # send_otp_email(user.email, otp)

        print(f"Resent OTP: {otp}")

        return Response({"message": "OTP resent successfully"}, status=200)
class UpdateProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        user = request.user

        username = request.data.get("username")
        email = request.data.get("email")
        phone = request.data.get("phone")
        address = request.data.get("address")
        zip_code = request.data.get("zip_code")
        profile_image = request.FILES.get("profile_image")

        # update normal fields
        if username:
            user.username = username

        if phone:
            user.phone = phone

        if address:
            user.address = address

        if zip_code:
            user.zip_code = zip_code

        if profile_image:
            user.profile_image = profile_image

        # ✅ EMAIL CHANGE FLOW (OTP REQUIRED)
        if email and email != user.email:

            if User.objects.filter(email=email).exclude(id=user.id).exists():
                return Response({"error": "Email already in use"}, status=400)

            otp = str(random.randint(100000, 999999))

            # store temporarily (5–10 min expiry)
            cache.set(f"email_change_{user.id}", {
                "email": email,
                "otp": otp
            }, timeout=600)

            # send OTP (reuse your existing email system)
            send_mail(
                subject="Email Change OTP",
                message=f"Your OTP for email change is {otp}",
                from_email="no-reply@yourapp.com",
                recipient_list=[email],
            )

            return Response({
                "message": "OTP sent to new email. Please verify to complete change."
            }, status=200)

        user.save()

        return Response({
            "message": "Profile updated successfully",
        }, status=200)
class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not old_password or not new_password:
            return Response(
                {"error": "Old password and new password are required"},
                status=400
            )

        # ✅ Check old password
        if not user.check_password(old_password):
            return Response({"error": "Old password is incorrect"}, status=400)

        # ✅ Set new password (IMPORTANT: use set_password)
        user.set_password(new_password)
        user.save()

        return Response({"message": "Password updated successfully"}, status=200)
class RequestEmailOtpAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response({"error": "Email required"}, status=400)

        otp = str(random.randint(100000, 999999))

        # store OTP for 10 minutes
        cache.set(f"email_otp_{email}", otp, timeout=600)

        # send email
        send_mail(
            subject="Email Change OTP",
            message=f"Your OTP is {otp}",
            from_email="no-reply@yourapp.com",
            recipient_list=[email],
        )

        return Response({"message": "OTP sent successfully"}, status=200)
class VerifyEmailChangeOTPAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        otp_input = request.data.get("otp")

        data = cache.get(f"email_change_{user.id}")

        if not data:
            return Response({"error": "OTP expired or not found"}, status=400)

        if data["otp"] != otp_input:
            return Response({"error": "Invalid OTP"}, status=400)

        user.email = data["email"]
        user.save()

        cache.delete(f"email_change_{user.id}")

        return Response({"message": "Email updated successfully"}, status=200)
class RequestEmailOtpAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response({"error": "Email required"}, status=400)

        user = request.user

        otp = str(random.randint(100000, 999999))

        # ✅ FIX: store using user.id (NOT email)
        cache.set(
            f"email_change_{user.id}",
            {
                "email": email,
                "otp": otp
            },
            timeout=600
        )

        send_mail(
            subject="Email Change OTP",
            message=f"Your OTP is {otp}",
            from_email="no-reply@yourapp.com",
            recipient_list=[email],
        )

        return Response({"message": "OTP sent successfully"}, status=200)
class DriverLoginAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user

        if user.role not in ("DELIVERY", "PICKUP"):
            return Response(
                {'error': 'Not a driver or picker account'},
                status=status.HTTP_403_FORBIDDEN
            )

        is_online = request.data.get("is_online")
        return Response({
            "is_online": user.is_online
        })

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response(
                {'error': 'Username and password required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Authenticate directly using username
        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is None:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 🚚 DRIVER ROLE CHECK
        if user.role not in ("DELIVERY", "PICKUP"):
            return Response(
                {'error': 'Not a driver or picker account'},
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'phone': user.phone,
            'address': user.address,
            'role': user.role,
        }, status=status.HTTP_200_OK)
class DriverOrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        user = request.user

        if user.role not in ("DELIVERY", "PICKUP"):
            return Response(
                {'error': 'Not a driver or picker account'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            order = Order.objects.select_related("user").get(id=order_id)

            # 🚚 check assignment table (IMPORTANT FIX)
            assignment = DeliveryAssignment.objects.filter(
                order=order,
                driver=user
            ).first()

            if not assignment:
                return Response(
                    {"error": "You are not assigned to this order"},
                    status=403
                )

            return Response({
                "order_id": order.id,
                "order_status": order.order_status,
                "payment_status": order.payment_status,
                "total_amount": order.total_amount,
                "payment_method": order.payment_method,

                # 👤 customer info
                "customer": {
                    "name": order.user.username,
                    "phone": order.user.phone,
                    "email": order.user.email,

                    # 👤 profile image
                    "profile_image": (
                        request.build_absolute_uri(order.user.profile_image.url)
                        if order.user.profile_image
                        else None
                    ),
                },

                # 📍 address
                "address": order.address_snapshot or order.user.address,

                # 🚚 assignment info
                "assignment_status": assignment.status,
                "assigned_at": assignment.assigned_at,
            })

        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_device_token(request):
    token = request.data.get('fcm_token')
    if not token:
        return Response({'error': 'fcm_token is required'}, status=400)
    
    request.user.fcm_token = token
    request.user.save()
    
    return Response({'success': True})