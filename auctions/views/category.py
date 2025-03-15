"""
Category management views for the auctions app.
"""

from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
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

    # Cache the list view for 1 hour since categories rarely change
    @method_decorator(cache_page(60 * 60))
    def list(self, request, *args, **kwargs):
        """List all categories with caching"""
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Get a single category with caching"""
        # Try to get from cache first
        pk = self.kwargs.get("pk")
        cache_key = f"category_{pk}"
        cached_data = cache.get(cache_key)

        if cached_data:
            return cached_data

        # If not in cache, get from database and cache
        response = super().retrieve(request, *args, **kwargs)
        cache.set(cache_key, response, 60 * 60)  # Cache for 1 hour
        return response
