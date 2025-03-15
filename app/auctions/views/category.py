"""
Category management views for the auctions app.
"""

import logging

from django.core.cache import cache
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated

from auctions.models import Category
from auctions.serializers import CategorySerializer

# Setup logger
logger = logging.getLogger(__name__)

# Cache timeouts
CATEGORY_CACHE_TIMEOUT = 60 * 60  # 1 hour


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

    def list(self, request, *args, **kwargs):
        """
        List all categories with caching
        """
        cache_key = "category_list"
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.debug("Returning cached category list")
            return cached_data

        response = super().list(request, *args, **kwargs)

        # Cache the response
        cache.set(cache_key, response, CATEGORY_CACHE_TIMEOUT)
        logger.debug("Caching category list")

        return response

    def create(self, request, *args, **kwargs):
        """Create a category and invalidate cache"""
        response = super().create(request, *args, **kwargs)
        cache.delete("category_list")
        return response

    def update(self, request, *args, **kwargs):
        """Update a category and invalidate cache"""
        response = super().update(request, *args, **kwargs)
        cache.delete("category_list")
        return response

    def destroy(self, request, *args, **kwargs):
        """Delete a category and invalidate cache"""
        response = super().destroy(request, *args, **kwargs)
        cache.delete("category_list")
        return response
