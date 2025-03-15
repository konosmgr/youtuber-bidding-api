"""
Admin-specific views for the auctions app.
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from auctions.models import Item, User
from auctions.serializers import ItemSerializer

# Setup logger
logger = logging.getLogger(__name__)

# Cache timeouts
ADMIN_CACHE_TIMEOUT = 10 * 60  # 10 minutes


@api_view(["GET"])
@permission_classes([IsAdminUser])
def recent_winners(request):
    """Get recent winners for admin dashboard"""
    try:
        # Try to get from cache
        cache_key = "admin_recent_winners"
        cached_response = cache.get(cache_key)
        if cached_response:
            logger.debug("Serving recent winners from cache")
            return cached_response

        # Get all completed auctions with winners in the last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)

        # Get items with winner assigned and ended in last 30 days
        # Using values() for a more efficient query
        recent_items = (
            Item.objects.filter(
                winner__isnull=False, end_date__lt=timezone.now(), end_date__gt=thirty_days_ago
            )
            .select_related("winner")
            .order_by("-end_date")
            .values(
                "id",
                "title",
                "end_date",
                "winner_contacted",
                "current_price",
                "winner_id",
                "winner__email",
                "winner__full_name",
                "winner__username",
            )
        )

        # Transform to the expected response format
        data = []
        for item in recent_items:
            data.append(
                {
                    "item_id": item["id"],
                    "title": item["title"],
                    "end_date": item["end_date"],
                    "winner_id": item["winner_id"],
                    "winner_email": item["winner__email"],
                    "winner_name": item["winner__full_name"] or item["winner__username"],
                    "contacted": item["winner_contacted"] is not None,
                    "final_price": float(item["current_price"]),
                }
            )

        response = Response(data)

        # Cache the response
        cache.set(cache_key, response, ADMIN_CACHE_TIMEOUT)
        logger.debug("Caching recent winners")

        return response

    except Exception as e:
        logger.error(f"Error in recent_winners: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def winner_ids(request):
    """Get IDs of users who have won auctions"""
    try:
        # Try to get from cache
        cache_key = "admin_winner_ids"
        cached_response = cache.get(cache_key)
        if cached_response:
            logger.debug("Serving winner IDs from cache")
            return cached_response

        # Get all unique user IDs who have won auctions
        winner_ids = (
            Item.objects.filter(winner__isnull=False, end_date__lt=timezone.now())
            .values_list("winner_id", flat=True)
            .distinct()
        )

        response = Response({"ids": list(winner_ids)})

        # Cache the response
        cache.set(cache_key, response, ADMIN_CACHE_TIMEOUT)
        logger.debug("Caching winner IDs")

        return response

    except Exception as e:
        logger.error(f"Error in winner_ids: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def user_won_items(request, user_id):
    """Get items won by a specific user"""
    try:
        # Create a cache key including the user ID
        cache_key = f"user_won_items_{user_id}"
        cached_response = cache.get(cache_key)
        if cached_response:
            logger.debug(f"Serving won items for user {user_id} from cache")
            return cached_response

        # Check if user exists
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": f"User with ID {user_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get items won by this user with optimized query
        won_items = (
            Item.objects.filter(winner_id=user_id)
            .select_related("category")
            .prefetch_related("images", "bids")
            .order_by("-end_date")
        )

        # Serialize the items
        serializer = ItemSerializer(won_items, many=True)

        response = Response(serializer.data)

        # Cache the response
        cache.set(cache_key, response, ADMIN_CACHE_TIMEOUT)
        logger.debug(f"Caching won items for user {user_id}")

        return response

    except Exception as e:
        logger.error(f"Error in user_won_items: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def mark_winner_contacted(request, item_id):
    """Mark that a winner has been contacted for an item"""
    try:
        # This is a state-changing operation, so we need to invalidate cache
        item = Item.objects.get(id=item_id)

        if not item.winner:
            return Response(
                {"detail": "Item does not have a winner"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update the item
        item.winner_contacted = timezone.now()
        item.save()

        # Invalidate related caches
        cache.delete("admin_recent_winners")
        cache.delete(f"user_won_items_{item.winner.id}")

        return Response({"status": "success", "contacted_at": item.winner_contacted})

    except Item.DoesNotExist:
        return Response(
            {"detail": f"Item with ID {item_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        logger.error(f"Error in mark_winner_contacted: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
