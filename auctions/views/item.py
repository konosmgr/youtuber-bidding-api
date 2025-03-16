"""
Item management views for the auctions app.
"""

import io
import logging
import os
import time
import traceback
import uuid
from typing import Any, Dict, Tuple

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q, QuerySet
from django.utils import timezone
from PIL import Image
from rest_framework import pagination, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from auctions.models import Bid, BidAttempt, Item, ItemImage, User
from auctions.serializers import BidSerializer, ItemSerializer
from auctions.views.utils import check_bid_rate_limit, log_error, send_outbid_notification

# Setup logger
logger = logging.getLogger(__name__)

# Cache timeout - use the value from settings or default to 1 hour
CACHE_TTL = getattr(settings, "CACHE_TTL", 60 * 60)

# Define shorter cache times for volatile data (5 minutes)
SHORT_CACHE_TTL = 60 * 5

# WebP quality setting
WEBP_QUALITY = 85


def process_image_with_webp(image_file, unique_name: str) -> Tuple[Dict[str, Any], bytes, bytes]:
    """
    Process an image file to create both original and WebP versions.

    Args:
        image_file: The uploaded image file
        unique_name: Base filename without extension

    Returns:
        Tuple containing:
            - dict with metadata (width, height)
            - original file content bytes
            - WebP file content bytes
    """
    try:
        # Store original content
        image_file.seek(0)
        original_content = image_file.read()

        # Open with PIL
        image_file.seek(0)
        img = Image.open(image_file)

        # Get image dimensions
        width, height = img.size

        # Create WebP version
        webp_buffer = io.BytesIO()
        img.save(webp_buffer, "WEBP", quality=WEBP_QUALITY)
        webp_content = webp_buffer.getvalue()

        # Log size difference
        original_size = len(original_content)
        webp_size = len(webp_content)
        reduction = 100 - (webp_size / original_size * 100) if original_size > 0 else 0
        logger.info(
            f"Image conversion: Original: {original_size} bytes, WebP: {webp_size} bytes, Reduction: {reduction:.1f}%"
        )

        return (
            {
                "width": width,
                "height": height,
            },
            original_content,
            webp_content,
        )

    except Exception as e:
        logger.error(f"Error processing WebP conversion: {str(e)}")
        # If there's an error, return the original content without WebP conversion
        image_file.seek(0)
        original_content = image_file.read()
        return {}, original_content, b""


# OPTIMIZATION NOTES:
# 1. Database Optimizations:
#    - Used select_related and prefetch_related to reduce N+1 query problems
#    - Added specific query optimizations based on the view action (list vs retrieve)
#    - Used annotations for counts to avoid additional queries
#
# 2. Caching Strategy:
#    - Implemented Redis caching for list and detail views
#    - Used shorter cache times for list views (more volatile)
#    - Longer cache times for detail views (less volatile)
#    - Proper cache invalidation when items are modified
#
# 3. Image Processing:
#    - Fixed issue with image uploads during item creation


class ItemViewSet(viewsets.ModelViewSet):
    """ViewSet for managing auction items"""

    queryset = (
        Item.objects.all().select_related("category", "winner").prefetch_related("images", "bids")
    )
    serializer_class = ItemSerializer
    pagination_class = pagination.PageNumberPagination

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
            item = self.perform_create(serializer)
            save_time = time.time() - save_start
            logger.info(f"Time to save item: {save_time:.4f}s")
            logger.info(f"Created item ID: {item.id}")

            # Process images if any are present
            image_processing_start = time.time()
            if images:
                import boto3
                from django.conf import settings
                from django.db import transaction

                # Set up S3 client
                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                )

                created_images = []
                with transaction.atomic():
                    for idx, image in enumerate(images):
                        try:
                            # Validate image type early to fail fast
                            if not image.content_type or not image.content_type.startswith(
                                "image/"
                            ):
                                logger.warning(f"File {image.name} is not a valid image")
                                continue

                            # Generate a unique filename
                            file_extension = os.path.splitext(image.name)[1].lower()
                            unique_name = f"{uuid.uuid4().hex}{file_extension}"

                            # Create WebP version with same unique ID but different extension
                            webp_name = f"{uuid.uuid4().hex}.webp"

                            # Process image to get both original and WebP versions
                            metadata, original_content, webp_content = process_image_with_webp(
                                image, unique_name
                            )

                            # Create database record
                            img = ItemImage(item=item, order=idx)
                            if metadata:
                                img.width = metadata.get("width", 0)
                                img.height = metadata.get("height", 0)
                            img.save()  # Save once to get ID

                            # Save original image
                            img.image.save(unique_name, ContentFile(original_content), save=True)

                            # Upload WebP version directly to S3 if conversion was successful
                            if webp_content:
                                s3_webp_key = f"images/{webp_name}"
                                s3.put_object(
                                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                                    Key=s3_webp_key,
                                    Body=webp_content,
                                    ContentType="image/webp",
                                    CacheControl="max-age=31536000",  # 1 year
                                )
                                # Store the WebP S3 key for future retrieval
                                img.webp_key = s3_webp_key
                                img.save()

                            logger.info(
                                f"Saved image {img.pk} for item {item.pk}, path: {img.image.name}"
                            )
                            created_images.append(img)
                        except Exception as e:
                            logger.error(f"Error processing image: {str(e)}")
                            logger.error(traceback.format_exc())

                image_processing_time = time.time() - image_processing_start
                logger.info(
                    f"Time to process {len(created_images)} images: {image_processing_time:.4f}s"
                )

            # Refresh serializer with saved data including images
            # Use a fresh serializer to ensure we have the latest data including the ID
            serializer = self.get_serializer(item)
            response_data = serializer.data

            # Ensure ID is included in the response
            if "id" not in response_data:
                response_data["id"] = item.id

            total_time = time.time() - start_time
            logger.info(f"Total time to create item: {total_time:.4f}s")

            return Response(response_data, status=status.HTTP_201_CREATED)
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
        # Type annotation for DRF request
        request = self.request  # type: Request

        queryset = (
            Item.objects.all()
            .select_related("category", "winner")
            .prefetch_related("images", "bids")
        )

        # Filter by category if provided
        category = request.query_params.get("category", None)
        if category:
            queryset = queryset.filter(category__code=category)

        # Filter by active status if provided
        active = request.query_params.get("active", None)
        if active is not None:
            is_active = active.lower() == "true"
            if is_active:
                # Active auctions are those that haven't ended yet
                queryset = queryset.filter(end_date__gt=timezone.now(), is_active=True)
            else:
                # Past auctions are those that have ended
                queryset = queryset.filter(end_date__lte=timezone.now())

        # Add annotations for counts to avoid N+1 queries
        queryset = queryset.annotate(
            image_count=Count("images", distinct=True),
            bid_count=Count("bids", distinct=True),
            highest_bid=Max("bids__amount"),
        )

        return queryset

    @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated])
    def add_images(self, request, pk=None):
        """Add new images to an existing item - optimized for better performance"""
        try:
            item = self.get_object()
            images = request.FILES.getlist("images")

            if not images:
                return Response(
                    {"detail": "No images provided"}, status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Adding {len(images)} images to item {item.id}")

            # Import dependencies
            import boto3
            from django.conf import settings
            from django.db import transaction

            # Set up S3 client
            s3 = boto3.client(
                "s3",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )

            created_images = []
            errors = []

            # Process images in a transaction for atomicity
            with transaction.atomic():
                for idx, image in enumerate(images):
                    try:
                        # Validate image type early to fail fast
                        if not image.content_type or not image.content_type.startswith("image/"):
                            errors.append(f"File {image.name} is not a valid image")
                            continue

                        # Generate a unique filename
                        file_extension = os.path.splitext(image.name)[1].lower()
                        unique_name = f"{uuid.uuid4().hex}{file_extension}"
                        webp_name = f"{uuid.uuid4().hex}.webp"

                        # Process image to get both original and WebP versions
                        metadata, original_content, webp_content = process_image_with_webp(
                            image, unique_name
                        )

                        # Create database record with optimized save operation
                        img = ItemImage(item=item, order=idx)
                        if metadata:
                            img.width = metadata.get("width", 0)
                            img.height = metadata.get("height", 0)
                        img.save()  # Save once to get ID

                        # Save original image
                        img.image.save(unique_name, ContentFile(original_content), save=True)

                        # Upload WebP version directly to S3 if conversion was successful
                        if webp_content:
                            s3_webp_key = f"images/{webp_name}"
                            s3.put_object(
                                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                                Key=s3_webp_key,
                                Body=webp_content,
                                ContentType="image/webp",
                                CacheControl="max-age=31536000",  # 1 year
                            )
                            # Store the WebP S3 key for future retrieval
                            img.webp_key = s3_webp_key
                            img.save()

                        logger.info(
                            f"Saved image {img.pk} for item {item.pk}, path: {img.image.name}, with WebP version"
                        )
                        created_images.append(img)

                    except Exception as e:
                        logger.error(f"Error processing image: {str(e)}")
                        logger.error(traceback.format_exc())
                        errors.append(f"Error processing image {image.name}: {str(e)}")

            # Return appropriate response based on success/failure
            if created_images:
                response_data = {
                    "message": f"Successfully uploaded {len(created_images)} images",
                }
                if errors:
                    response_data["errors"] = ", ".join(errors)

                return Response(response_data, status=status.HTTP_201_CREATED)
            else:
                return Response(
                    {"detail": "Failed to upload any images", "errors": ", ".join(errors)},
                    status=status.HTTP_400_BAD_REQUEST,
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

            # Check rate limiting first before any database operations
            if check_bid_rate_limit(user, ip_address):
                return Response(
                    {"detail": "Too many bid attempts. Please try again later."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            # Validate bid amount early to fail fast
            try:
                amount = float(request.data.get("amount", 0))
                if amount <= 0:
                    return Response(
                        {"detail": "Invalid bid amount"}, status=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid bid amount"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Get item with related objects in a single query
            try:
                item = Item.objects.select_related("category").get(pk=pk)
            except Item.DoesNotExist:
                return Response({"detail": "Item not found"}, status=status.HTTP_404_NOT_FOUND)

            # Record bid attempt
            bid_attempt = BidAttempt.objects.create(user=user, ip_address=ip_address, success=False)

            # Check if auction is active and hasn't ended
            if not item.is_active or item.end_date < timezone.now():
                return Response(
                    {"detail": "This auction is not available for bidding"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get previous highest bid in a single efficient query
            previous_highest_bid = None
            previous_highest_bidder = None

            # Fetch the highest bid with a single query
            if Bid.objects.filter(item=item).exists():
                previous_highest_bid = (
                    Bid.objects.filter(item=item).order_by("-amount").select_related("user").first()
                )
                if previous_highest_bid:
                    previous_highest_bidder = previous_highest_bid.user

            # Validate amount against current price
            if amount <= float(item.current_price):
                return Response(
                    {"detail": f"Bid must be higher than current price of ${item.current_price}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if amount < float(item.current_price) + 1:
                return Response(
                    {"detail": "Minimum bid increment is $1.00"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Pre-validate the bid to catch ValidationError before creating
            max_allowed = 0
            if previous_highest_bid:
                max_allowed = previous_highest_bid.amount * 2
                if amount > max_allowed:
                    return Response(
                        {
                            "detail": f"Bid cannot exceed {int(max_allowed)}$ (100% more than current bid)"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Create new bid and update item price in a transaction
            from decimal import Decimal

            from django.db import transaction

            with transaction.atomic():
                bid = Bid.objects.create(item=item, user=user, amount=amount)

                # Update item price - convert to Decimal to avoid float precision issues
                item.current_price = Decimal(str(amount))
                item.save(update_fields=["current_price"])

                # Mark bid attempt as successful
                bid_attempt.success = True
                bid_attempt.save(update_fields=["success"])

            # Send outbid notification if there was a previous bidder
            if previous_highest_bidder and previous_highest_bidder != user:
                # Check if previous highest bidder has outbid notifications enabled
                if previous_highest_bidder.outbid_notifications_enabled:
                    # Only access amount if previous_highest_bid is not None
                    prev_amount = previous_highest_bid.amount if previous_highest_bid else 0
                    send_outbid_notification(
                        previous_highest_bidder,
                        item,
                        prev_amount,
                        amount,
                    )

            return Response(BidSerializer(bid).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            # Use the new error logging function
            error_id = log_error(
                "place_bid",
                e,
                {
                    "user_id": getattr(request.user, "id", None),
                    "item_id": pk,
                    "amount": request.data.get("amount") if hasattr(request, "data") else None,
                },
            )

            # Return a user-friendly error with the ID for support reference
            return Response(
                {
                    "detail": f"An error occurred while processing your bid. Error ID: {error_id}",
                    "error_id": error_id,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    def perform_create(self, serializer):
        """Override perform_create to return the created item"""
        item = serializer.save()
        return item


@api_view(["GET"])
@permission_classes([AllowAny])
def past_auctions(request):
    """Return past (ended) auctions with pagination and caching"""
    try:
        # Get pagination parameters
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))

        # Generate cache key based on pagination parameters
        cache_key = f"past_auctions_p{page}_s{page_size}"

        # Try to get from cache first
        from django.core.cache import cache

        cached_response = cache.get(cache_key)
        if cached_response:
            return cached_response

        # Get the current time
        now = timezone.now()

        # Optimize query with annotations and prefetching
        queryset = (
            Item.objects.filter(end_date__lt=now)
            .order_by("-end_date")
            .select_related("category", "winner")
            .prefetch_related("images", "bids")
            .annotate(
                image_count=Count("images", distinct=True),
                bid_count=Count("bids", distinct=True),
                highest_bid=Max("bids__amount"),
            )
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

        # Cache for 5 minutes - adjust based on your needs
        cache.set(cache_key, response, 300)

        return response

    except Exception as e:
        logger.error(f"Error in past_auctions: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
