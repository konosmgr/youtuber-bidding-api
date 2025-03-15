"""
Item management views for the auctions app.
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, BasePermission, IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from auctions.models import Bid, Item, ItemImage
from auctions.serializers import ItemSerializer

# Setup logger
logger = logging.getLogger(__name__)

# Cache timeouts
ACTIVE_ITEMS_CACHE_TIMEOUT = 5 * 60  # 5 minutes
PAST_AUCTIONS_CACHE_TIMEOUT = 15 * 60  # 15 minutes


class ItemViewSet(viewsets.ModelViewSet):
    """ViewSet for managing auction items"""

    queryset = Item.objects.all()
    serializer_class = ItemSerializer

    def get_permissions(self) -> List[BasePermission]:
        """Get permissions based on action"""
        if self.action in ["list", "retrieve"]:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
            if self.action in ["create", "update", "partial_update", "destroy"]:
                # Cast to avoid type errors
                permission_classes.extend([IsAdminUser()])
        return [permission() for permission in permission_classes]

    def create(self, request, *args, **kwargs):
        """Create a new auction item"""
        start_time = time.time()
        try:
            # Validate and save the item first
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

            # Save the new item
            item = serializer.save()

            # Invalidate relevant caches
            self._invalidate_item_caches()

            # Return the newly created item
            response_time = time.time() - start_time
            logger.info(f"Created item in {response_time:.4f}s: {item.title}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            error_time = time.time() - start_time
            logger.exception(f"Error creating item after {error_time:.4f}s: {str(e)}")
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        """Handle updates for items"""
        try:
            # Get the existing item
            instance = self.get_object()

            # Partial update - only update fields that are included
            serializer = self.get_serializer(
                instance, data=request.data, partial=True  # Allow partial updates
            )

            if not serializer.is_valid():
                return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

            # Save the updated item
            self.perform_update(serializer)

            # Invalidate relevant caches
            self._invalidate_item_caches(instance.id)

            # Return the updated item
            return Response(serializer.data)

        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        """Delete an item and invalidate caches"""
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        self._invalidate_item_caches(instance.id)
        return response

    def get_queryset(self) -> QuerySet:
        """
        Get queryset with filtering and caching

        Uses caching for active item lists and category-filtered lists
        to improve performance.
        """
        # Get query parameters from request
        request = self.request
        category = (
            request.query_params.get("category", None) if hasattr(request, "query_params") else None
        )
        active_param = (
            request.query_params.get("active", None) if hasattr(request, "query_params") else None
        )

        # Determine if we can use cache
        use_cache = self.request.method.lower() == "get" and self.action == "list"
        cache_key = None

        if use_cache:
            # Create cache key based on parameters
            cache_key = "items"
            if category:
                cache_key += f"_cat_{category}"
            if active_param is not None:
                cache_key += f"_active_{active_param}"

            # Try to get from cache
            cached_queryset = cache.get(cache_key)
            if cached_queryset:
                logger.debug(f"Serving items from cache: {cache_key}")
                return cached_queryset

        # Build the queryset with optimizations
        queryset = (
            Item.objects.all()
            .select_related("category", "winner")
            .prefetch_related("images", "bids")
        )

        # Filter by category if provided
        if category:
            queryset = queryset.filter(category__code=category)

        # Filter by active status if provided
        if active_param is not None:
            is_active = active_param.lower() == "true"
            if is_active:
                # Active auctions are those that haven't ended yet
                queryset = queryset.filter(end_date__gt=timezone.now(), is_active=True)
            else:
                # Past auctions are those that have ended
                queryset = queryset.filter(end_date__lte=timezone.now())

        # Cache the queryset if needed
        if use_cache and cache_key and active_param == "true":
            # Only cache active items (they change less frequently)
            cache.set(cache_key, queryset, ACTIVE_ITEMS_CACHE_TIMEOUT)
            logger.debug(f"Caching items: {cache_key}")

        return queryset

    def _invalidate_item_caches(self, item_id=None):
        """Invalidate item-related caches when data changes"""
        # Pattern-based cache invalidation with wildcard
        keys_to_delete = []

        # Invalidate general item lists
        keys_to_delete.append("items_active_true")
        keys_to_delete.append("items")

        # If we have the item, invalidate category-specific caches
        if item_id:
            try:
                item = Item.objects.get(id=item_id)
                if item.category:
                    keys_to_delete.append(f"items_cat_{item.category.code}")
                    keys_to_delete.append(f"items_cat_{item.category.code}_active_true")
            except Item.DoesNotExist:
                pass

        # Delete all relevant keys
        for key in keys_to_delete:
            cache.delete(key)

        # Also invalidate past_auctions cache
        # In Django, we need to use more basic methods for cache key pattern matching
        all_keys = cache._cache.keys("*past_auctions*")  # type: ignore
        if all_keys:
            for key in all_keys:
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                if "past_auctions" in key:
                    cache.delete(key)

        logger.debug(f"Invalidated item caches: {', '.join(keys_to_delete)}")


@api_view(["GET"])
@permission_classes([AllowAny])
def past_auctions(request):
    """Return past (ended) auctions with pagination"""
    try:
        # Get pagination parameters
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))
        category = request.query_params.get("category", "")

        # Create a cache key based on the parameters
        cache_key = f"past_auctions_p{page}_s{page_size}"
        if category:
            cache_key += f"_c{category}"

        # Try to get from cache
        cached_response = cache.get(cache_key)
        if cached_response:
            logger.debug(f"Serving past auctions from cache: {cache_key}")
            return cached_response

        # Get the current time
        now = timezone.now()

        # Build the query
        query = Q(end_date__lt=now)
        if category:
            query &= Q(category__code=category)

        # Query past auctions with optimized queryset
        queryset = (
            Item.objects.filter(query)
            .order_by("-end_date")
            .select_related("category", "winner")
            .prefetch_related("images", "bids")
        )

        # Apply pagination
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages

        # Handle page out of range
        if page > total_pages and total_pages > 0:
            page = total_pages

        items = paginator.get_page(page)

        # Serialize the results
        serializer = ItemSerializer(items, many=True)

        # Prepare response
        response = Response(
            {"items": serializer.data, "page": page, "pages": total_pages, "count": paginator.count}
        )

        # Cache the response
        cache.set(cache_key, response, PAST_AUCTIONS_CACHE_TIMEOUT)
        logger.debug(f"Caching past auctions: {cache_key}")

        return response

    except Exception as e:
        logger.error(f"Error in past_auctions: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
