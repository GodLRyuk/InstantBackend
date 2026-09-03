import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Address

User = get_user_model()

GOOGLE_MAPS_API_KEY = "AIzaSyA_P5OTNZ0c7K9FLy2x6VMjiYl5SmcvNIc"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def geocode_address(full_address, city, state, pincode, landmark=None):
    """
    Geocode once, at write time, so both the customer app and driver
    app read the same stored lat/lng instead of each guessing on their
    own (or falling back to a coarse pincode centroid).
    Returns (lat, lng) or (None, None) if geocoding fails.
    """
    parts = [landmark, full_address, city, state, pincode]
    query = ", ".join([p.strip() for p in parts if p and str(p).strip()])
    query = f"{query}, India"

    try:
        params = {"address": query, "key": GOOGLE_MAPS_API_KEY}
        if pincode:
            params["components"] = f"postal_code:{pincode}|country:IN"

        resp = requests.get(GEOCODE_URL, params=params, timeout=5)
        if resp.status_code != 200:
            return None, None

        data = resp.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None, None

        location = data["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    except requests.RequestException:
        return None, None


class AddAddressAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        full_address = request.data.get("full_address")
        city = request.data.get("city")
        state = request.data.get("state")
        pincode = request.data.get("pincode")
        landmark = request.data.get("landmark")

        lat, lng = geocode_address(full_address, city, state, pincode, landmark)

        address = Address.objects.create(
            user=user,
            full_address=full_address,
            name=request.data.get("name"),
            phone=request.data.get("phone"),
            city=city,
            state=state,
            pincode=pincode,
            lat=lat,
            lng=lng,
            address_type=request.data.get("address_type", "HOME"),
            landmark=landmark,
            is_default=request.data.get("is_default", False),
        )

        return Response({
            "message": "Address added successfully",
            "address_id": address.id,
            "geocoded": lat is not None,
        }, status=status.HTTP_201_CREATED)


class ListAddressAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
                "landmark": a.landmark,
                "type": a.address_type,
                "is_default": a.is_default,
                "lat": a.lat,
                "lng": a.lng,
            })

        return Response(data)


class DeleteAddressAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, id):
        user = request.user

        try:
            address = Address.objects.get(id=id, user=user)
            address.delete()
            return Response({"message": "Deleted successfully"})
        except Address.DoesNotExist:
            return Response({"error": "Not found"}, status=404)