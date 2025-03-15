"""
Utility functions for the auctions views.
"""

import logging
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from auctions.models import BidAttempt, LoginAttempt, User

# Setup logger
logger = logging.getLogger(__name__)

# Constants for rate limiting
MAX_LOGIN_ATTEMPTS = 5  # Max attempts per 15 minutes
LOGIN_ATTEMPT_PERIOD = 15 * 60  # 15 minutes in seconds
MAX_BID_ATTEMPTS = 10  # Max bid attempts per minute
BID_ATTEMPT_PERIOD = 60  # 1 minute in seconds


def verify_recaptcha(recaptcha_response):
    """Verify reCAPTCHA response"""
    # For development, always return True
    return True

    try:
        recaptcha_secret = settings.RECAPTCHA_SECRET_KEY
        recaptcha_url = "https://www.google.com/recaptcha/api/siteverify"
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
    """Send email verification link to user"""
    try:
        # Generate verification token and expiration
        token = uuid.uuid4().hex
        token_expires = timezone.now() + timedelta(days=2)

        # Save token to user
        user.verification_token = token
        user.verification_token_expires = token_expires
        user.save()

        # Build verification link
        verification_link = f"{settings.FRONTEND_URL}/verify-email/{token}"

        # Render email template
        context = {
            "user": user,
            "verification_link": verification_link,
        }
        email_html = render_to_string("verification_email.html", context)
        email_text = render_to_string("verification_email.txt", context)

        # Send email
        send_mail(
            subject="Verify Your Account",
            message=email_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=email_html,
            fail_silently=False,
        )

        return True
    except Exception as e:
        logger.error(f"Error sending verification email: {str(e)}")
        return False


def send_outbid_notification(user, item, previous_bid, new_bid):
    """Send outbid notification to a user"""
    try:
        # Render email template
        context = {
            "user": user,
            "item": item,
            "previous_bid": previous_bid,
            "new_bid": new_bid,
            "item_url": f"{settings.FRONTEND_URL}/items/{item.id}",
        }
        email_html = render_to_string("outbid_notification.html", context)
        email_text = render_to_string("outbid_notification.txt", context)

        # Send email
        send_mail(
            subject=f"You've been outbid on {item.title}",
            message=email_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=email_html,
            fail_silently=False,
        )

        return True
    except Exception as e:
        logger.error(f"Error sending outbid notification: {str(e)}")
        return False
