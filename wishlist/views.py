from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Wishlist
from .serializers import WishlistSerializer

class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Fetch all wishlist items for the logged-in user"""
        items = Wishlist.objects.filter(user=request.user).select_related('product')
        serializer = WishlistSerializer(items, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        """Add a product to wishlist"""
        serializer = WishlistSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        """Remove a product from wishlist"""
        product_id = request.data.get('product_id')
        deleted, _ = Wishlist.objects.filter(
            user=request.user,
            product_id=product_id
        ).delete()
        if deleted:
            return Response({'message': 'Removed from wishlist'})
        return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)