from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class DriverStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    # GET → load status
    def get(self, request):
        user = request.user

        if user.role != "DELIVERY":
            return Response({"error": "Not a driver"}, status=403)

        return Response({
            "is_online": user.is_online
        })

    # POST → update status
    def post(self, request):
        user = request.user

        if user.role != "DELIVERY":
            return Response({"error": "Not a driver"}, status=403)

        is_online = request.data.get("is_online")

        if is_online is None:
            return Response({"error": "is_online required"}, status=400)

        user.is_online = is_online
        user.save()

        return Response({
            "is_online": user.is_online
        })