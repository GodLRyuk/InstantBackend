from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import ProductReview
from .serializers import ProductReviewSerializer

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def product_reviews(request, product_id):

    # GET reviews for product
    if request.method == 'GET':
        reviews = ProductReview.objects.filter(product_id=product_id)
        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(serializer.data)

    # POST review for product
    if request.method == 'POST':
        review, created = ProductReview.objects.update_or_create(
            product_id=product_id,
            user=request.user,
            defaults={
                'rating': request.data.get('rating'),
                'comment': request.data.get('comment', '')
            }
        )

        serializer = ProductReviewSerializer(review)
        return Response(serializer.data)