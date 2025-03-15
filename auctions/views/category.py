"""
Category management views for the auctions app.
"""

from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated

from auctions.models import Category
from auctions.serializers import CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for category management"""

    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated, IsAdminUser]
        return [permission() for permission in permission_classes]
