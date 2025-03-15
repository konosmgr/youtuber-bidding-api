"""
Admin-specific views for the auctions app.
"""

import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from auctions.models import Item, User
from auctions.serializers import ItemSerializer

# Setup logger
logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def recent_winners(request):
    """Get recent winners for admin dashboard"""
    try:
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
                    "contacted": item["winner_contacted"],
                    "final_price": float(item["current_price"]),
                }
            )

        return Response(data)

    except Exception as e:
        logger.error(f"Error in recent_winners: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def user_won_items(request, user_id):
    """Get items won by a specific user"""
    try:
        # Verify user exists
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": f"User with ID {user_id} not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Get items won by this user with optimized query
        won_items = (
            Item.objects.filter(winner=user)
            .select_related("category", "winner")
            .prefetch_related("images", "bids")
            .order_by("-end_date")
        )

        # Serialize items
        serializer = ItemSerializer(won_items, many=True)

        return Response(serializer.data)

    except Exception as e:
        logger.error(f"Error in user_won_items: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def winner_ids(request):
    """Get list of user IDs who have won at least one auction"""
    try:
        # Get unique winner IDs with a more efficient query
        # Use values() to fetch all required fields in a single query
        winners = (
            User.objects.filter(won_items__isnull=False)
            .distinct()
            .values("id", "email", "username", "full_name")
        )

        # The values() method returns dictionaries, so we can return them directly
        return Response(list(winners))

    except Exception as e:
        logger.error(f"Error in winner_ids: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def mark_winners(request):
    """Mark winners for completed auctions"""
    try:
        item_ids = request.data.get("item_ids", [])

        if not item_ids:
            return Response({"detail": "No item IDs provided"}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        for item_id in item_ids:
            try:
                item = Item.objects.get(id=item_id)

                # Check if auction has ended
                if item.end_date > timezone.now():
                    results.append(
                        {"item_id": item_id, "success": False, "error": "Auction has not ended yet"}
                    )
                    continue

                # Check if there are bids
                if not item.bids.exists():
                    results.append(
                        {"item_id": item_id, "success": False, "error": "No bids on this item"}
                    )
                    continue

                # Get highest bidder
                highest_bid = item.bids.first()  # Assuming ordered by -amount
                winner = highest_bid.user

                # Assign winner
                item.winner = winner
                item.save()

                results.append(
                    {
                        "item_id": item_id,
                        "success": True,
                        "winner_id": winner.id,
                        "winner_email": winner.email,
                    }
                )

            except Item.DoesNotExist:
                results.append({"item_id": item_id, "success": False, "error": "Item not found"})
            except Exception as item_error:
                results.append({"item_id": item_id, "success": False, "error": str(item_error)})

        return Response(
            {
                "results": results,
                "total": len(results),
                "successful": sum(1 for r in results if r.get("success", False)),
            }
        )

    except Exception as e:
        logger.error(f"Error in mark_winners: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def contact_winners(request):
    """Mark winners as contacted"""
    try:
        item_ids = request.data.get("item_ids", [])

        if not item_ids:
            return Response({"detail": "No item IDs provided"}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        for item_id in item_ids:
            try:
                item = Item.objects.get(id=item_id)

                # Check if winner is assigned
                if not item.winner:
                    results.append(
                        {"item_id": item_id, "success": False, "error": "No winner assigned"}
                    )
                    continue

                # Mark as contacted
                item.winner_contacted = True
                item.winner_contacted_date = timezone.now()
                item.save()

                results.append(
                    {
                        "item_id": item_id,
                        "success": True,
                        "winner_id": item.winner.id,
                        "winner_email": item.winner.email,
                    }
                )

            except Item.DoesNotExist:
                results.append({"item_id": item_id, "success": False, "error": "Item not found"})
            except Exception as item_error:
                results.append({"item_id": item_id, "success": False, "error": str(item_error)})

        return Response(
            {
                "results": results,
                "total": len(results),
                "successful": sum(1 for r in results if r.get("success", False)),
            }
        )

    except Exception as e:
        logger.error(f"Error in contact_winners: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
