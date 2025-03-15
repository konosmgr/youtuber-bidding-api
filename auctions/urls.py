from django.urls import include, path
from rest_framework.routers import DefaultRouter

from auctions.views import admin, auth, category, item, message, user

from . import views_analytics

router = DefaultRouter()
router.register(r"items", item.ItemViewSet)
router.register(r"categories", category.CategoryViewSet)
router.register(r"users", user.UserViewSet)
router.register(r"messages", message.MessageViewSet, basename="messages")

urlpatterns = [
    path("", include(router.urls)),
    path("csrf/", auth.get_csrf_token, name="csrf"),
    path("register/", auth.register_user, name="register"),
    path("login/", auth.login_view, name="login"),
    path("google-auth/", auth.google_auth, name="google_auth"),
    path("logout/", auth.logout_view, name="logout"),
    path("verify-email/<str:token>/", auth.verify_email, name="verify_email"),
    path("resend-verification/", auth.resend_verification, name="resend_verification"),
    path(
        "messages/user/<int:user_id>/",
        message.MessageViewSet.as_view({"get": "user_chat"}),
        name="user-chat",
    ),
    path("debug-message/", message.debug_send_message, name="debug_message"),
    path("analytics/overview/", views_analytics.analytics_overview, name="analytics_overview"),
    path("analytics/users/", views_analytics.user_metrics, name="user_metrics"),
    path("analytics/auctions/", views_analytics.auction_metrics, name="auction_metrics"),
    path("analytics/top-items/", views_analytics.top_items, name="top_items"),
    path("check-nickname/", user.check_nickname_availability, name="check_nickname"),
    path("items/past/", item.past_auctions, name="past_auctions"),
    path("admin/recent-winners/", admin.recent_winners, name="admin_recent_winners"),
    path("admin/user-won-items/<int:user_id>/", admin.user_won_items, name="user_won_items"),
    path("admin/winner-ids/", admin.winner_ids, name="winner_ids"),
    # Keep only the dropdown winner assignment endpoint
    path("admin/mark_winners/", admin.mark_winners, name="mark_winners"),
    path("admin/contact_winners/", admin.contact_winners, name="contact_winners"),
]
