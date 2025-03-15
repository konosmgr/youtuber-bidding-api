"""
Views package for the auctions app.
This module imports all views from the submodules to maintain API compatibility.
"""

from auctions.views.admin import (
    contact_winners,
    mark_winners,
    recent_winners,
    user_won_items,
    winner_ids,
)

# Import all views to maintain compatibility
from auctions.views.auth import (
    get_csrf_token,
    google_auth,
    login_view,
    logout_view,
    register_user,
    resend_verification,
    verify_email,
)
from auctions.views.category import CategoryViewSet
from auctions.views.item import ItemViewSet, past_auctions
from auctions.views.message import MessageViewSet, debug_send_message
from auctions.views.user import UserViewSet, check_nickname_availability

# Keep all exports as part of the public API
__all__ = [
    "register_user",
    "login_view",
    "logout_view",
    "google_auth",
    "verify_email",
    "resend_verification",
    "get_csrf_token",
    "ItemViewSet",
    "past_auctions",
    "CategoryViewSet",
    "UserViewSet",
    "check_nickname_availability",
    "MessageViewSet",
    "debug_send_message",
    "recent_winners",
    "user_won_items",
    "winner_ids",
    "mark_winners",
    "contact_winners",
]
