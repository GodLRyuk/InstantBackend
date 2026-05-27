from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Address
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated


User = get_user_model()
class AddAddressAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):

        user = request.user

        address = Address.objects.create(
            user=user,
            full_address=request.data.get("full_address"),
            name=request.data.get("name"),
            phone=request.data.get("phone"),
            city=request.data.get("city"),
            state=request.data.get("state"),
            pincode=request.data.get("pincode"),
            address_type=request.data.get("address_type", "HOME"),
            is_default=request.data.get("is_default", False),
        )

        return Response({
            "message": "Address added successfully",
            "address_id": address.id
        }, status=status.HTTP_201_CREATED)
class AddAddressAPIView(APIView):

    def post(self, request):

        user = request.user

        address = Address.objects.create(
            user=user,
            full_address=request.data.get("full_address"),
            name=request.data.get("name"),
            phone=request.data.get("phone"),
            city=request.data.get("city"),
            state=request.data.get("state"),
            pincode=request.data.get("pincode"),
            address_type=request.data.get("address_type", "HOME"),
            is_default=request.data.get("is_default", False),
        )

        return Response({
            "message": "Address added successfully",
            "address_id": address.id
        }, status=status.HTTP_201_CREATED)

class ListAddressAPIView(APIView):

    def get(self, request):

        user = request.user
        addresses = user.addresses.all()

        data = []

        for a in addresses:
            data.append({
                "id": a.id,
                "full_address": a.full_address,
                "name": a.name,
                "phone": a.phone,
                "city": a.city,
                "state": a.state,
                "pincode": a.pincode,
                "type": a.address_type,
                "is_default": a.is_default
            })

        return Response(data)
class DeleteAddressAPIView(APIView):

    def delete(self, request, id):

        user = request.user

        try:
            address = Address.objects.get(id=id, user=user)
            address.delete()
            return Response({"message": "Deleted successfully"})
        except Address.DoesNotExist:
            return Response({"error": "Not found"}, status=404)