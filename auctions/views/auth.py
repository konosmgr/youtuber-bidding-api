"""
Authentication related views for the auctions app.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from auctions.models import LoginAttempt, User
from auctions.serializers import (
    GoogleAuthSerializer,
    LoginSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)
from auctions.views.utils import check_login_rate_limit, send_verification_email, verify_recaptcha

# Setup logger
logger = logging.getLogger(__name__)


@api_view(["GET"])
@ensure_csrf_cookie
def get_csrf_token(request):
    """Get CSRF token"""
    return Response({"detail": "CSRF cookie set"})


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
    """User login with rate limiting and enhanced debugging"""
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    # Get client IP
    ip_address = request.META.get("REMOTE_ADDR")

    # Add debug logging
    print(f"Login attempt for email: {email} from IP: {ip_address}")

    # Check rate limit
    if check_login_rate_limit(email, ip_address):
        # Record failed attempt
        LoginAttempt.objects.create(email=email, ip_address=ip_address, success=False)

        print(f"Rate limit exceeded for {email}")
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
        print(f"CAPTCHA required for {email}")
        return Response(
            {"detail": "CAPTCHA verification required", "captcha_required": True},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if captcha_required and not verify_recaptcha(request.data.get("captcha_response")):
        # Record failed attempt
        LoginAttempt.objects.create(email=email, ip_address=ip_address, success=False)

        print(f"Invalid CAPTCHA for {email}")
        return Response({"detail": "Invalid CAPTCHA response."}, status=status.HTTP_400_BAD_REQUEST)

    # Try to authenticate
    try:
        # Find the user by email
        user = User.objects.get(email=email)
        print(f"Found user {user.username} with email {email}")
        print(f"Email verified status: {user.email_verified}")

        # Check for email verification
        if not user.email_verified:
            # Record failed attempt
            LoginAttempt.objects.create(email=email, ip_address=ip_address, success=False)

            print(f"Email not verified for {email}")

            # Debug verification info
            print(f"Verification token: {user.verification_token}")
            print(f"Token expires: {user.verification_token_expires}")

            # Generate a new token if needed
            if not user.verification_token or user.verification_token_expires < timezone.now():
                print(f"Generating new verification token for {email}")
                # Generate a new token
                send_verification_email(user)

            return Response(
                {
                    "detail": "Please verify your email before logging in.",
                    "email_verification_required": True,
                    "email": email,  # Send back the email to make resending easier
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Attempt to authenticate the user
        print(f"Authenticating user {user.username} with provided password")
        user = authenticate(request, username=user.username, password=password)

        if user is not None:
            login(request, user)
            # Save the session explicitly
            request.session.save()

            print(f"Login successful for {email}, session key: {request.session.session_key}")

            # Record successful login
            LoginAttempt.objects.create(email=email, ip_address=ip_address, success=True)

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
            LoginAttempt.objects.create(email=email, ip_address=ip_address, success=False)

            print(f"Invalid password for {email}")
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    except User.DoesNotExist:
        # Record failed attempt
        LoginAttempt.objects.create(email=email, ip_address=ip_address, success=False)

        print(f"User not found for email: {email}")
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


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
            logger.error(f"Google token verification error: {str(verify_error)}", exc_info=True)
            return Response(
                {"detail": f"Failed to verify Google token: {str(verify_error)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Extract user info
        google_id = id_info["sub"]
        email = id_info["email"]
        email_verified = id_info.get("email_verified", False)

        logger.info(f"Extracted user info from token - email: {email}, verified: {email_verified}")

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
                logger.info(f"Found existing user with email: {email}. Updating with Google ID.")
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
                    logger.error(f"Error creating user: {str(create_error)}", exc_info=True)
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
    """Logout the current user"""
    logout(request)
    return Response({"status": "success"})


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email(request, token):
    """Email verification endpoint"""
    try:
        user = User.objects.get(verification_token=token)

        # Check if token is expired
        if user.verification_token_expires < timezone.now():
            # Generate a new token
            send_verification_email(user)
            return Response(
                {"detail": "Verification link expired. A new link has been sent to your email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Mark email as verified
        user.email_verified = True
        user.verification_token = ""  # Clear token
        user.save()

        return Response({"detail": "Email verified successfully!"})

    except User.DoesNotExist:
        return Response(
            {"detail": "Invalid verification token."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_verification(request):
    """Resend email verification link"""
    email = request.data.get("email")
    if not email:
        return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)

        # Check if already verified
        if user.email_verified:
            return Response({"detail": "Email is already verified."})

        # Send new verification email
        email_sent = send_verification_email(user)

        if email_sent:
            return Response({"detail": "Verification email sent."})
        else:
            return Response(
                {"detail": "Failed to send verification email."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    except User.DoesNotExist:
        # For security, don't reveal that the email doesn't exist
        return Response({"detail": "Verification email sent if user exists."})
