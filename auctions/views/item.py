"""
Item management views for the auctions app.
"""

import logging
import os
import time
import traceback
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.paginator import Paginator
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from auctions.models import Bid, BidAttempt, Item, ItemImage, User
from auctions.serializers import BidSerializer, ItemSerializer
from auctions.views.utils import check_bid_rate_limit, send_outbid_notification

# Setup logger
logger = logging.getLogger(__name__)


class ItemViewSet(viewsets.ModelViewSet):
    """ViewSet for managing auction items"""

    queryset = Item.objects.all().order_by("-created_at")
    serializer_class = ItemSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [AllowAny]
        elif self.action in [
            "create",
            "update",
            "partial_update",
            "destroy",
            "add_images",
            "delete_images",
        ]:
            permission_classes = [IsAuthenticated, IsAdminUser]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def list(self, request, *args, **kwargs):
        start_time = time.time()

        # Log the start of the request
        logger.info(f"Started loading items list at: {start_time}")

        # Timing the queryset evaluation
        queryset_start = time.time()
        queryset = self.filter_queryset(self.get_queryset())
        queryset_time = time.time() - queryset_start
        logger.info(f"Time to get and filter queryset: {queryset_time:.4f}s")

        # Timing the pagination
        page_start = time.time()
        page = self.paginate_queryset(queryset)
        page_time = time.time() - page_start
        logger.info(f"Time to paginate queryset: {page_time:.4f}s")

        if page is not None:
            # Timing the serialization
            serializer_start = time.time()
            serializer = self.get_serializer(page, many=True)
            serializer_time = time.time() - serializer_start
            logger.info(f"Time to serialize paginated data: {serializer_time:.4f}s")

            response_time = time.time() - start_time
            logger.info(f"Total time to process list request: {response_time:.4f}s")
            return self.get_paginated_response(serializer.data)

        # Timing the serialization (no pagination)
        serializer_start = time.time()
        serializer = self.get_serializer(queryset, many=True)
        serializer_time = time.time() - serializer_start
        logger.info(f"Time to serialize all data: {serializer_time:.4f}s")

        response_time = time.time() - start_time
        logger.info(f"Total time to process list request: {response_time:.4f}s")
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        start_time = time.time()
        logger.info(f"Started item creation at: {start_time}")

        try:
            # Debug logs
            logger.info(f"Received data: {request.data}")
            logger.info(f"Files in request: {request.FILES}")

            # Check for multiple images
            images = request.FILES.getlist("images")
            logger.info(f"Found {len(images)} images: {[img.name for img in images]}")

            serializer_start = time.time()
            serializer = self.get_serializer(data=request.data)
            serializer_time = time.time() - serializer_start
            logger.info(f"Time to initialize serializer: {serializer_time:.4f}s")

            validation_start = time.time()
            if not serializer.is_valid():
                logger.error(f"Serializer errors: {serializer.errors}")
                return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            validation_time = time.time() - validation_start
            logger.info(f"Time to validate data: {validation_time:.4f}s")

            save_start = time.time()
            self.perform_create(serializer)
            save_time = time.time() - save_start
            logger.info(f"Time to save item: {save_time:.4f}s")

            total_time = time.time() - start_time
            logger.info(f"Total time to create item: {total_time:.4f}s")

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

            # Return the updated item
            return Response(serializer.data)

        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get_queryset(self):
        queryset = Item.objects.all()

        # Filter by category if provided
        category = self.request.query_params.get("category", None)
        if category:
            queryset = queryset.filter(category__code=category)

        # Filter by active status if provided
        active = self.request.query_params.get("active", None)
        if active is not None:
            is_active = active.lower() == "true"
            if is_active:
                # Active auctions are those that haven't ended yet
                queryset = queryset.filter(end_date__gt=timezone.now(), is_active=True)
            else:
                # Past auctions are those that have ended
                queryset = queryset.filter(end_date__lte=timezone.now())

        return queryset

    @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated])
    def add_images(self, request, pk=None):
        """Add new images to an existing item"""
        try:
            item = self.get_object()
            images = request.FILES.getlist("images")

            if not images:
                return Response(
                    {"detail": "No images provided"}, status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Adding {len(images)} images to item {item.id}")

            created_images = []
            for idx, image in enumerate(images):
                try:
                    # Generate a unique filename
                    file_extension = os.path.splitext(image.name)[1].lower()
                    unique_name = f"{uuid.uuid4().hex}{file_extension}"
                    s3_key = f"images/{unique_name}"

                    # Create database record
                    img = ItemImage.objects.create(item=item, order=idx)

                    # Save the image
                    img.image = image
                    img.save()

                    logger.info(f"Saved image {img.id} for item {item.id}")
                    created_images.append(img)

                except Exception as e:
                    logger.error(f"Error processing image: {str(e)}")
                    logger.error(traceback.format_exc())

            return Response(
                {"message": f"Successfully uploaded {len(created_images)} images"},
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Overall exception in add_images: {str(e)}")
            logger.error(traceback.format_exc())
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated])
    def delete_images(self, request, pk=None):
        """Delete specified images from an item"""
        try:
            item = self.get_object()
            image_ids = request.data.get("image_ids", [])

            if not image_ids:
                return Response(
                    {"detail": "No image IDs provided"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            logger.info(f"Deleting images with IDs: {image_ids} from item {item.id}")

            # Delete specified images
            deleted_count = 0
            for image_id in image_ids:
                try:
                    image = ItemImage.objects.get(id=image_id, item=item)
                    # Delete the actual file if it exists
                    if image.image:
                        if os.path.isfile(image.image.path):
                            os.remove(image.image.path)
                    image.delete()
                    deleted_count += 1
                    logger.info(f"Deleted image ID: {image_id}")
                except ItemImage.DoesNotExist:
                    logger.warning(f"Image ID {image_id} not found or does not belong to this item")
                except Exception as e:
                    logger.error(f"Error deleting image {image_id}: {str(e)}")

            # Return success response
            return Response(
                {"detail": f"Successfully deleted {deleted_count} images"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception(f"Error in delete_images: {str(e)}")
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def place_bid(self, request, pk=None):
        """Place bid with rate limiting and user authentication, respecting notification preferences"""
        try:
            user = request.user
            ip_address = request.META.get("REMOTE_ADDR")

            # Check rate limiting
            if check_bid_rate_limit(user, ip_address):
                return Response(
                    {"detail": "Too many bid attempts. Please try again later."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            # Record bid attempt
            bid_attempt = BidAttempt.objects.create(user=user, ip_address=ip_address, success=False)

            item = self.get_object()

            # Check if auction is active
            if not item.is_active:
                return Response(
                    {"detail": "This auction is not active"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if auction has ended
            if item.end_date < timezone.now():
                return Response(
                    {"detail": "This auction has ended"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate bid amount
            amount = request.data.get("amount")
            if not amount:
                return Response(
                    {"detail": "Bid amount is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Convert to Decimal instead of float to avoid warnings
            try:
                amount = Decimal(str(amount))
            except (ValueError, TypeError, InvalidOperation):
                return Response(
                    {"detail": "Invalid bid amount"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Get current highest bid and bidder
            previous_highest_bid = None
            previous_highest_bidder = None

            if item.bids.exists():
                previous_highest_bid = item.bids.first()  # Due to ordering = ['-amount']
                previous_highest_bidder = previous_highest_bid.user

            # Convert item.current_price to Decimal for comparison
            current_price = Decimal(str(item.current_price))
            if amount <= current_price:
                return Response(
                    {"detail": f"Bid must be higher than current price of ${item.current_price}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if amount < current_price + Decimal("1.00"):
                return Response(
                    {"detail": "Minimum bid increment is $1.00"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Pre-validate the bid to catch ValidationError before creating
            max_allowed = 0
            if item.bids.exists():
                highest_bid = item.bids.first()
                max_allowed = highest_bid.amount * 2
                if amount > max_allowed:
                    return Response(
                        {
                            "detail": f"Bid cannot exceed {int(max_allowed)}$ (100% more than current bid)"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Create new bid (now should be safe from ValidationError)
            try:
                bid = Bid.objects.create(item=item, user=user, amount=amount)

                # Update item price
                item.current_price = amount
                item.save()

                # Mark bid attempt as successful
                bid_attempt.success = True
                bid_attempt.save()

                # Send outbid notification if there was a previous bidder
                if previous_highest_bidder and previous_highest_bidder != user:
                    # Check if previous highest bidder has outbid notifications enabled
                    if previous_highest_bidder.outbid_notifications_enabled:
                        send_outbid_notification(
                            previous_highest_bidder,
                            item,
                            previous_highest_bid.amount,
                            amount,
                        )

                return Response(BidSerializer(bid).data, status=status.HTTP_201_CREATED)
            except Exception as create_error:
                logger.error(f"Error creating bid: {str(create_error)}")
                return Response({"detail": str(create_error)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Bid error: {str(e)}")
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([AllowAny])
def past_auctions(request):
    """Return past (ended) auctions with pagination"""
    try:
        # Get pagination parameters
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))

        # Get the current time
        now = timezone.now()

        # Query past auctions with consistent ordering
        queryset = Item.objects.filter(end_date__lt=now).order_by("-end_date")

        # Apply pagination
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages

        # Handle page out of range
        if page > total_pages and total_pages > 0:
            page = total_pages

        items = paginator.get_page(page)

        # Serialize the results
        serializer = ItemSerializer(items, many=True)

        # Return paginated response
        return Response(
            {"items": serializer.data, "page": page, "pages": total_pages, "count": paginator.count}
        )

    except Exception as e:
        logger.error(f"Error in past_auctions: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
