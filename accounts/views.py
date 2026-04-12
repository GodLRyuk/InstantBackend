# accounts/api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

class AdminLoginAPIView(APIView):

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response(
                {'error': 'Email and password required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find user by email
        try:
            user_obj = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Authenticate using username
        user = authenticate(
            request,
            username=user_obj.username,
            password=password
        )

        if user is None:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_staff:
            return Response(
                {'error': 'Not an admin user'},
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user_id': user.id,
            'email': user.email,
            'phone': user.phone,
            'address': user.address,
            'is_staff': user.is_staff
        })
        
class RegisterAPIView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        User = get_user_model() 
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
            return Response(
                {"error": "Email already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(phone=phone).exists():
            return Response(
                {"error": "Phone already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            phone=phone,
            address=address,
            zip_code=zip_code
            role=role
        )

        return Response({
            "message": "User registered successfully",
            "user_id": user.id
        }, status=status.HTTP_201_CREATED)