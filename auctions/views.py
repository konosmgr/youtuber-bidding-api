import json
import logging
import os
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Q
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import (
    Bid,
    BidAttempt,
    Category,
    Item,
    ItemImage,
    LoginAttempt,
    Message,
    User,
)
from .serializers import (
    BidSerializer,
    CategorySerializer,
    GoogleAuthSerializer,
    ItemSerializer,
    LoginSerializer,
    MessageSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)

# Setup logger
logger = logging.getLogger(__name__)

# Constants for rate limiting
MAX_LOGIN_ATTEMPTS = 5  # Max attempts per 15 minutes
LOGIN_ATTEMPT_PERIOD = 15 * 60  # 15 minutes in seconds
MAX_BID_ATTEMPTS = 10  # Max bid attempts per minute
BID_ATTEMPT_PERIOD = 60  # 1 minute in seconds


# Helper functions
def verify_recaptcha(recaptcha_response):
    """Verify reCAPTCHA response"""
    # For development, always return True
    return True

    try:
        payload = {"secret": recaptcha_secret, "response": recaptcha_response}
        response = requests.post(recaptcha_url, data=payload)
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        logger.error(f"reCAPTCHA verification error: {str(e)}")
        return False


def check_login_rate_limit(email, ip_address):
    """Check if login attempts exceed rate limit"""
    cutoff_time = timezone.now() - timedelta(seconds=LOGIN_ATTEMPT_PERIOD)
    attempts = LoginAttempt.objects.filter(
        email=email, ip_address=ip_address, timestamp__gte=cutoff_time, success=False
    ).count()

    return attempts >= MAX_LOGIN_ATTEMPTS


def check_bid_rate_limit(user, ip_address):
    """Check if bid attempts exceed rate limit"""
    cutoff_time = timezone.now() - timedelta(seconds=BID_ATTEMPT_PERIOD)
    query = {"ip_address": ip_address, "timestamp__gte": cutoff_time}

    if user and user.is_authenticated:
        query["user"] = user

    attempts = BidAttempt.objects.filter(**query).count()
    return attempts >= MAX_BID_ATTEMPTS


def send_verification_email(user):
    """Send email verification to user"""
    # Generate verification token
    token = uuid.uuid4().hex
    user.verification_token = token
    user.verification_token_expires = timezone.now() + timedelta(hours=24)
    user.save()

    # Build verification URL
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    verification_url = f"{frontend_url}/verify-email/{token}"

    # Build email context
    context = {"user": user, "verification_url": verification_url, "expiry_hours": 24}

    # Create email body
    html_message = render_to_string("emails/email_verification.html", context)
    plain_message = (
        f"Please verify your email by clicking this link: {verification_url}"
    )

    # Send email
    try:
        send_mail(
            subject="Verify your email for Alaska Auctions",
            message=plain_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email: {str(e)}")
        return False


@api_view(["GET"])
@ensure_csrf_cookie
@permission_classes([AllowAny])
def get_csrf_token(request):
    """Endpoint to get CSRF token"""
    return Response({"csrfToken": get_token(request)})


@api_view(["GET"])
@permission_classes([AllowAny])
def past_auctions(request):
    """Get all completed auctions with optional filtering by category"""
    try:
        # Get query parameters
        category = request.query_params.get("category", "")

        # Build the query - get auctions where end_date has passed
        query = Q(end_date__lt=timezone.now())

        # Apply category filter if provided
        if category:
            query &= Q(category__code=category)

        # Get items
        items = Item.objects.filter(query).order_by("-end_date")

        # Simple response without pagination (easier to debug)
        serializer = ItemSerializer(items, many=True)
        return Response(serializer.data)

    except Exception as e:
        logger.error(f"Error fetching past auctions: {str(e)}")
        # Return an empty list instead of an error for better UX
        return Response([])


@api_view(["POST"])
@permission_classes([AllowAny])
def register_user(request):
    """User registration endpoint with CAPTCHA verification"""
    serializer = UserRegistrationSerializer(data=request.data)

    if serializer.is_valid():
        captcha_response = request.data.get("captcha_response")
        if not verify_recaptcha(captcha_response):
            return Response(
                {"captcha_response": "Invalid CAPTCHA response."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.save()
        user.email_verified = True  # Auto-verify during development
        user.save()

        # Send verification email
        email_sent = send_verification_email(user)

        return Response(
            {
                "message": "User registered successfully. Please verify your email.",
                "email_sent": email_sent,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@ensure_csrf_cookie
@permission_classes([AllowAny])
def login_view(request):
    """User login with rate limiting"""
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    # Get client IP
    ip_address = request.META.get("REMOTE_ADDR")

    # Check rate limit
    if check_login_rate_limit(email, ip_address):
        # Record failed attempt
        LoginAttempt.objects.create(email=email, ip_address=ip_address, success=False)

        return Response(
            {"detail": f"Too many failed login attempts. Try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Check if captcha is required (for suspicious activity)
    captcha_required = (
        LoginAttempt.objects.filter(
            email=email,
            ip_address=ip_address,
            timestamp__gte=timezone.now() - timedelta(hours=24),
            success=False,
        ).count()
        >= 3
    )

    if captcha_required and not request.data.get("captcha_response"):
        return Response(
            {"detail": "CAPTCHA verification required", "captcha_required": True},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if captcha_required and not verify_recaptcha(request.data.get("captcha_response")):
        # Record failed attempt
        LoginAttempt.objects.create(email=email, ip_address=ip_address, success=False)

        return Response(
            {"detail": "Invalid CAPTCHA response."}, status=status.HTTP_400_BAD_REQUEST
        )

    # Try to authenticate
    try:
        user = User.objects.get(email=email)
        user = authenticate(request, username=user.username, password=password)

        if user is not None:
            login(request, user)
            # Save the session explicitly (add this line)
            request.session.save()

            # Record successful login
            LoginAttempt.objects.create(
                email=email, ip_address=ip_address, success=True
            )

            return Response(
                {
                    "user": UserSerializer(user).data,
                    "message": "Login successful",
                    # Include session key for debugging (optional)
                    "session_key": request.session.session_key,
                }
            )
        else:
            # Record failed attempt
            LoginAttempt.objects.create(
                email=email, ip_address=ip_address, success=False
            )

            return Response(
                {"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

    except User.DoesNotExist:
        # Record failed attempt
        LoginAttempt.objects.create(email=email, ip_address=ip_address, success=False)

        return Response(
            {"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def google_auth(request):
    """Google authentication endpoint"""
    serializer = GoogleAuthSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    token = serializer.validated_data["token"]

    try:
        # Log token details (truncated for security)
        if token and len(token) > 10:
            token_preview = f"{token[:5]}...{token[-5:]}"
            logger.info(f"Processing Google auth with token: {token_preview}")

        # Verify the token with Google
        try:
            # Log the client ID being used (truncated for security)
            client_id = settings.GOOGLE_CLIENT_ID
            if client_id and len(client_id) > 10:
                client_id_preview = f"{client_id[:5]}...{client_id[-5:]}"
                logger.info(f"Using Google client ID: {client_id_preview}")

            # Add a debug log for Google verification
            logger.info("Starting Google token verification")
            id_info = id_token.verify_oauth2_token(
                token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
            )
            logger.info("Successfully verified Google token")

        except Exception as verify_error:
            logger.error(
                f"Google token verification error: {str(verify_error)}", exc_info=True
            )
            return Response(
                {"detail": f"Failed to verify Google token: {str(verify_error)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Extract user info
        google_id = id_info["sub"]
        email = id_info["email"]
        email_verified = id_info.get("email_verified", False)

        logger.info(
            f"Extracted user info from token - email: {email}, verified: {email_verified}"
        )

        if not email_verified:
            return Response(
                {"detail": "Google email not verified"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user exists
        try:
            user = User.objects.get(google_id=google_id)
            logger.info(f"Found existing user with Google ID: {user.email}")
        except User.DoesNotExist:
            # Check if user with this email exists
            try:
                user = User.objects.get(email=email)
                logger.info(
                    f"Found existing user with email: {email}. Updating with Google ID."
                )
                # Update user with Google ID
                user.google_id = google_id
                if not user.profile_picture and "picture" in id_info:
                    user.profile_picture = id_info["picture"]
                user.save()
            except User.DoesNotExist:
                # Create new user
                logger.info(f"Creating new user for: {email}")
                username = email.split("@")[0]
                # Ensure username is unique
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{email.split('@')[0]}{counter}"
                    counter += 1

                try:
                    user = User.objects.create(
                        username=username,
                        email=email,
                        google_id=google_id,
                        email_verified=True,
                        is_active=True,
                    )

                    if "name" in id_info:
                        user.full_name = id_info["name"]
                    if "given_name" in id_info:
                        user.nickname = id_info["given_name"]
                    if "picture" in id_info:
                        user.profile_picture = id_info["picture"]

                    user.save()
                    logger.info(f"Created new user: {username}")
                except Exception as create_error:
                    logger.error(
                        f"Error creating user: {str(create_error)}", exc_info=True
                    )
                    return Response(
                        {"detail": f"Error creating user: {str(create_error)}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Log in the user
        try:
            logger.info(f"Attempting to log in user: {user.email}")
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            logger.info(f"User logged in successfully: {user.email}")
        except Exception as login_error:
            logger.error(f"Login error: {str(login_error)}", exc_info=True)
            return Response(
                {"detail": f"Error logging in: {str(login_error)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "user": UserSerializer(user).data,
                "message": "Google authentication successful",
            }
        )

    except Exception as e:
        logger.error(f"Google authentication error: {str(e)}", exc_info=True)
        return Response(
            {"detail": f"Google authentication failed: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@ensure_csrf_cookie
def logout_view(request):
    logout(request)
    return Response({"status": "success"})


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email(request, token):
    """Email verification endpoint"""
    try:
        user = User.objects.get(
            verification_token=token, verification_token_expires__gt=timezone.now()
        )
        user.email_verified = True
        user.verification_token = ""
        user.save()

        return Response({"message": "Email verified successfully"})
    except User.DoesNotExist:
        return Response(
            {"detail": "Invalid or expired verification token"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_verification(request):
    """Resend verification email"""
    email = request.data.get("email")
    if not email:
        return Response(
            {"detail": "Email is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email, email_verified=False)

        # Check if we can send another email (limit to once per hour)
        if (
            user.verification_token_expires
            and user.verification_token_expires > timezone.now() - timedelta(hours=23)
        ):
            time_remaining = (
                user.verification_token_expires - (timezone.now() - timedelta(hours=23))
            ).seconds // 60
            return Response(
                {
                    "detail": f"Please wait {time_remaining} minutes before requesting another verification email"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Send verification email
        email_sent = send_verification_email(user)

        return Response(
            {"message": "Verification email sent", "email_sent": email_sent}
        )
    except User.DoesNotExist:
        # Don't reveal that the email doesn't exist or is already verified
        return Response(
            {
                "message": "If your email exists and is not verified, a verification email has been sent"
            }
        )


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
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

    def create(self, request, *args, **kwargs):
        try:
            # Debug logs
            logger.info(f"Received data: {request.data}")
            logger.info(f"Files in request: {request.FILES}")

            # Check for multiple images
            images = request.FILES.getlist("images")
            logger.info(f"Found {len(images)} images: {[img.name for img in images]}")

            # Create serializer and validate data
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                logger.error(f"Serializer errors: {serializer.errors}")
                return Response(
                    {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
                )

            # Save the item first
            item = serializer.save()

            # Now attach the images to the item
            for index, image in enumerate(images):
                try:
                    img_obj = ItemImage.objects.create(
                        item=item, image=image, order=index
                    )
                    logger.info(
                        f"Created image {index} for item {item.id}: {image.name}"
                    )
                    logger.info(f"Image uploaded to: {img_obj.image.name}")
                    logger.info(f"Image URL: {img_obj.image.url}")
                except Exception as e:
                    logger.error(f"Error saving image {index}: {str(e)}")

            # Refresh the serializer with the updated item (including images)
            updated_serializer = self.get_serializer(item)
            return Response(updated_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception(f"Error creating item: {str(e)}")
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
                return Response(
                    {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
                )

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
            print(f"=== Starting add_images for item {pk} ===")

            if "images" not in request.FILES:
                return Response(
                    {"detail": "No images provided"}, status=status.HTTP_400_BAD_REQUEST
                )

            images = request.FILES.getlist("images")

            # Get credentials from Django settings
            from django.conf import settings

            # Add new images with incremented order values
            created_images = []
            for index, image in enumerate(images):
                try:
                    # Read the file content
                    file_content = image.read()
                    print(f"Read {len(file_content)} bytes from image")

                    # Reset file pointer
                    image.seek(0)

                    # First create the Django model object to get the correct path
                    img = ItemImage.objects.create(item=item, image=image)
                    print(f"Image object created with ID: {img.id}")
                    print(f"Path in database: {img.image.name}")

                    # Use boto3 to ensure the file is saved to the correct path
                    import boto3

                    s3 = boto3.client(
                        "s3",
                        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    )

                    # Use the actual path Django expects
                    print(f"Using Django's expected path: {img.image.name}")
                    s3.put_object(
                        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                        Key=img.image.name,
                        Body=file_content,
                        ContentType=getattr(
                            image, "content_type", "application/octet-stream"
                        ),
                    )
                    print(f"Direct upload successful to {img.image.name}")

                    created_images.append(img)
                except Exception as e:
                    print(f"Error processing image {index}: {str(e)}")
                    import traceback

                    traceback.print_exc()

            return Response(
                {"message": f"Successfully uploaded {len(created_images)} images"},
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            print(f"Overall exception: {str(e)}")
            import traceback

            traceback.print_exc()
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
                    logger.warning(
                        f"Image ID {image_id} not found or does not belong to this item"
                    )
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
        """Place bid with rate limiting and user authentication"""
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
            bid_attempt = BidAttempt.objects.create(
                user=user, ip_address=ip_address, success=False
            )

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

            try:
                amount = float(amount)
            except ValueError:
                return Response(
                    {"detail": "Invalid bid amount"}, status=status.HTTP_400_BAD_REQUEST
                )

            if amount <= float(item.current_price):
                return Response(
                    {
                        "detail": f"Bid must be higher than current price of ${item.current_price}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if amount < float(item.current_price) + 1:
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

                return Response(BidSerializer(bid).data, status=status.HTTP_201_CREATED)
            except Exception as create_error:
                logger.error(f"Error creating bid: {str(create_error)}")
                return Response(
                    {"detail": str(create_error)}, status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            logger.error(f"Bid error: {str(e)}")
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([AllowAny])
def check_nickname_availability(request):
    """Check if a nickname is available"""
    nickname = request.query_params.get("nickname", "").strip()

    if not nickname:
        return Response(
            {"detail": "Nickname parameter is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if nickname exists
    exists = User.objects.filter(nickname=nickname).exists()

    return Response({"nickname": nickname, "available": not exists})


class MessageViewSet(viewsets.ModelViewSet):
    """ViewSet for user-admin messaging"""

    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            # Admins can see all messages
            return Message.objects.all()
        else:
            # Regular users can only see their conversations
            return Message.objects.filter(
                models.Q(sender=user) | models.Q(receiver=user)
            )

    def create(self, request, *args, **kwargs):
        """Handle message creation with improved debugging and error handling"""
        try:
            user = request.user
            print(
                f"Message creation request from user: {user.username} (is_staff: {user.is_staff})"
            )
            print(f"Request data: {request.data}")

            # Prepare data for serialization
            message_data = request.data.copy()

            # Always set the sender to the current user
            message_data["sender"] = user.id

            # Handle receiver properly based on user type
            if (
                user.is_staff
                and "receiver" in request.data
                and request.data["receiver"]
            ):
                # Admin sending to specific user - use the provided receiver
                receiver_id = request.data["receiver"]
                print(f"Admin sending message to user ID: {receiver_id}")

                # Verify the receiver exists
                try:
                    receiver = User.objects.get(id=receiver_id)
                    print(f"Verified receiver exists: {receiver.username}")
                except User.DoesNotExist:
                    return Response(
                        {"detail": f"Receiver with ID {receiver_id} does not exist."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            elif not user.is_staff:
                # Regular user sending to admin - set receiver to null
                message_data["receiver"] = None
                print(f"User sending message to admin (receiver=null)")

            print(f"Final message data for serializer: {message_data}")

            # Create the serializer with our prepared data
            serializer = self.get_serializer(data=message_data)

            if not serializer.is_valid():
                print(f"Serializer validation errors: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Save the message
            message = serializer.save()
            print(f"Message created successfully: {message.id}")

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error creating message: {str(e)}")
            import traceback

            traceback.print_exc()
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def my_conversations(self, request):
        """Get conversations for current user"""
        user = request.user
        if user.is_staff:
            # For admins, get all unique users who have sent messages
            senders = User.objects.filter(
                sent_messages__receiver__isnull=True
            ).distinct()

            # Get latest message for each sender
            conversations = []
            for sender in senders:
                # Get all messages between this user and admin
                all_messages = Message.objects.filter(
                    models.Q(sender=sender, receiver__isnull=True)
                    | models.Q(sender__is_staff=True, receiver=sender)
                ).order_by("-created_at")

                # Get the latest message separately
                latest_message = all_messages.first()

                if latest_message:
                    # Count unread messages in a separate query
                    unread_count = Message.objects.filter(
                        sender=sender, receiver__isnull=True, is_read=False
                    ).count()

                    conversations.append(
                        {
                            "user": UserSerializer(sender).data,
                            "latest_message": MessageSerializer(latest_message).data,
                            "unread_count": unread_count,
                        }
                    )

            return Response(conversations)
        else:
            # For regular users, get their conversation with admin
            all_messages = Message.objects.filter(
                models.Q(sender=user, receiver__isnull=True)
                | models.Q(sender__is_staff=True, receiver=user)
            ).order_by("-created_at")

            # Get latest 10 messages
            messages = all_messages[:10]

            # Count unread in a separate query
            unread_count = Message.objects.filter(
                sender__is_staff=True, receiver=user, is_read=False
            ).count()

            return Response(
                {
                    "messages": MessageSerializer(messages, many=True).data,
                    "unread_count": unread_count,
                }
            )

    @action(detail=False, methods=["get"])
    def admin_chat(self, request):
        """Get messages between current user and admin"""
        user = request.user

        # Mark messages as read
        if not user.is_staff:
            Message.objects.filter(
                sender__is_staff=True, receiver=user, is_read=False
            ).update(is_read=True)

        # Get messages
        messages = Message.objects.filter(
            models.Q(sender=user, receiver__isnull=True)
            | models.Q(sender__is_staff=True, receiver=user)
        ).order_by("created_at")

        return Response(MessageSerializer(messages, many=True).data)

    @action(detail=False, methods=["get"])
    def user_chat(self, request, user_id=None):
        """Get messages between admin and a specific user"""
        if not request.user.is_staff:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            user_id = self.kwargs.get("user_id") or request.query_params.get("user_id")
            user = User.objects.get(id=user_id)

            # Mark messages as read
            Message.objects.filter(
                sender=user, receiver__isnull=True, is_read=False
            ).update(is_read=True)

            # Get messages
            messages = Message.objects.filter(
                models.Q(sender=user, receiver__isnull=True)
                | models.Q(sender__is_staff=True, receiver=user)
            ).order_by("created_at")

            return Response(MessageSerializer(messages, many=True).data)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
            )


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated, IsAdminUser]
        return [permission() for permission in permission_classes]


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for user management"""

    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action in ["retrieve", "update", "partial_update"]:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        # Users can only see their own profile
        if not self.request.user.is_staff:
            return User.objects.filter(id=self.request.user.id)
        return User.objects.all()

    @action(detail=False, methods=["get"])
    def me(self, request):
        """Get current user profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """Update user profile"""
        user = request.user
        print(f"Updating profile for user: {user.email}")
        print(f"Received data: {request.data}")

        # Create a serializer with the user and data
        serializer = self.get_serializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            # Save the updated user
            serializer.save()
            print(f"Profile updated successfully: {serializer.data}")
            return Response(serializer.data)

        print(f"Profile update validation errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def debug_send_message(request):
    """Debug endpoint to test message creation"""
    try:
        content = request.data.get("content")
        receiver_id = request.data.get("receiver")

        if not content:
            return Response(
                {"detail": "Content is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Handle receiver properly
        receiver = None
        if receiver_id:
            try:
                receiver = User.objects.get(id=receiver_id)
            except User.DoesNotExist:
                return Response(
                    {"detail": "Receiver not found"}, status=status.HTTP_404_NOT_FOUND
                )

        # Create message with proper receiver
        message = Message.objects.create(
            sender=request.user, content=content, receiver=receiver
        )

        # Return full serialized message
        return Response(MessageSerializer(message).data)
    except Exception as e:
        return Response(
            {"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def recent_winners(request):
    """Get recent auction winners for admin dashboard"""
    # Get items that have ended with a winner set
    recent_winners = Item.objects.filter(
        winner__isnull=False, end_date__lt=timezone.now()
    ).order_by("-end_date")[
        :10
    ]  # Last 10 winners

    result = []
    for item in recent_winners:
        result.append(
            {
                "item": {
                    "id": item.id,
                    "title": item.title,
                    "current_price": float(item.current_price),
                    "end_date": item.end_date,
                },
                "user": {
                    "id": item.winner.id,
                    "email": item.winner.email,
                    "nickname": item.winner.nickname or "",
                },
            }
        )

    return Response(result)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def user_won_items(request, user_id):
    """Get items that a specific user has won"""
    try:
        # Verify the user exists
        user = User.objects.get(id=user_id)

        # Find items won by this user
        won_items = Item.objects.filter(
            winner=user, end_date__lt=timezone.now()
        ).order_by("-end_date")

        # Format the response
        items_data = []
        for item in won_items:
            items_data.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "current_price": float(item.current_price),
                    "end_date": item.end_date,
                    "category": item.category.name,
                    "winner_notified": item.winner_notified,
                    "winner_contacted": item.winner_contacted,
                }
            )

        return Response({"user_id": user_id, "items": items_data})

    except User.DoesNotExist:
        return Response({"detail": f"User with ID {user_id} not found"}, status=404)
    except Exception as e:
        return Response({"detail": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def winner_ids(request):
    """Get IDs of users who have won auctions"""
    # Get all unique user IDs who have won auctions
    winner_ids = (
        Item.objects.filter(winner__isnull=False, end_date__lt=timezone.now())
        .values_list("winner_id", flat=True)
        .distinct()
    )

    return Response({"ids": list(winner_ids)})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def mark_winners(request):
    try:
        data = request.data
        item_ids = data.get("item_ids", [])

        print(f"Trying to mark winners for items: {item_ids}")

        if not item_ids:
            return Response(
                {"detail": "No items selected"}, status=status.HTTP_400_BAD_REQUEST
            )

        updated = 0
        for item_id in item_ids:
            try:
                item = Item.objects.get(pk=item_id)
                print(f"Processing item {item_id}: {item.title}")
                print(f"Has winner: {item.winner is not None}")
                print(f"Has bids: {item.bids.exists()}")

                # Explicitly check the bids count and print them
                bids_count = item.bids.count()
                print(f"Bids count: {bids_count}")

                if bids_count > 0:
                    print("Bids:")
                    for bid in item.bids.all():
                        print(f"  - Bid: {bid.amount} by {bid.user.email}")

                if not item.winner and item.bids.exists():
                    highest_bid = item.bids.order_by("-amount").first()
                    print(
                        f"Found highest bid: {highest_bid.amount} by {highest_bid.user.email}"
                    )
                    item.winner = highest_bid.user
                    item.save()
                    updated += 1
                    print(
                        f"Updated item {item_id} with winner: {highest_bid.user.email}"
                    )
                else:
                    print(f"Item {item_id} not eligible for update")
            except Item.DoesNotExist:
                print(f"Item {item_id} does not exist")
                continue
            except Exception as e:
                print(f"Error processing item {item_id}: {str(e)}")
                continue

        print(f"Updated {updated} items with winners")
        return Response({"updated": updated})
    except Exception as e:
        print(f"Error in mark_winners: {str(e)}")
        return Response(
            {"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def contact_winners(request):
    try:
        data = request.data
        item_ids = data.get("item_ids", [])

        if not item_ids:
            return Response(
                {"detail": "No items selected"}, status=status.HTTP_400_BAD_REQUEST
            )

        contacted = 0
        for item_id in item_ids:
            try:
                item = Item.objects.get(pk=item_id)
                if item.winner and not item.winner_notified:
                    # Send email notification
                    send_winner_notification(item)

                    # Create message in system
                    Message.objects.create(
                        sender=request.user,
                        receiver=item.winner,
                        content=f"Congratulations! You've won the auction for {item.title} with a bid of ${item.current_price}. Please respond to arrange payment and shipping details.",
                    )

                    item.winner_notified = True
                    item.winner_contacted = timezone.now()
                    item.save()
                    contacted += 1
            except Item.DoesNotExist:
                continue

        return Response({"contacted": contacted})
    except Exception as e:
        return Response(
            {"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def send_winner_notification(item):
    """Send email notification to auction winner"""
    from django.conf import settings
    from django.core.mail import send_mail

    subject = f"Congratulations! You've won the auction for {item.title}"
    message = f"""
    Dear {item.winner.nickname or item.winner.username},
    
    Congratulations! You've won the auction for {item.title} with your bid of ${item.current_price}.
    
    Please log in to your account and check your messages for details about completing the purchase.
    
    Thank you for participating in our auction!
    
    Alaska Auctions Team
    """

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[item.winner.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending winner notification email: {str(e)}")
        return False
