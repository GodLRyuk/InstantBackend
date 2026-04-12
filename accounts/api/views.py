from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, get_user_model
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

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
            'is_staff': user.is_staff
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
            "role": user.role
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

        if not username or not email or not password or not phone:
            return Response(
                {"error": "username, email, password and phone are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already exists"}, status=400)

        if User.objects.filter(phone=phone).exists():
            return Response({"error": "Phone already exists"}, status=400)

        # ADMIN LOGIC HERE
        if role == "ADMIN":
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                phone=phone,
                address=address,
                zip_code=zip_code,
                role=role,
                is_staff=True
            )
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                phone=phone,
                address=address,
                zip_code=zip_code,
                role=role
            )

        return Response({
            "message": "User registered successfully",
            "user_id": user.id
        }, status=status.HTTP_201_CREATED)