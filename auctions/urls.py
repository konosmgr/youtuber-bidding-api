from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views
from . import views_analytics

router = DefaultRouter()
router.register(r"items", views.ItemViewSet)
router.register(r"categories", views.CategoryViewSet)
router.register(r"users", views.UserViewSet)
router.register(r"messages", views.MessageViewSet, basename='messages')

urlpatterns = [
    path("", include(router.urls)),
    path("csrf/", views.get_csrf_token, name="csrf"),
    path("register/", views.register_user, name="register"),
    path("login/", views.login_view, name="login"),
    path("google-auth/", views.google_auth, name="google_auth"),
    path("logout/", views.logout_view, name="logout"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("resend-verification/", views.resend_verification, name="resend_verification"),
    path("messages/user/<int:user_id>/", views.MessageViewSet.as_view({'get': 'user_chat'}), name="user-chat"),
    path("debug-message/", views.debug_send_message, name="debug_message"),
    path("analytics/overview/", views_analytics.analytics_overview, name="analytics_overview"),
    path("analytics/users/", views_analytics.user_metrics, name="user_metrics"),
    path("analytics/auctions/", views_analytics.auction_metrics, name="auction_metrics"),
    path("analytics/top-items/", views_analytics.top_items, name="top_items"),
    path("check-nickname/", views.check_nickname_availability, name="check_nickname"),
    path("items/past/", views.past_auctions, name="past_auctions"),
    path("admin/recent-winners/", views.recent_winners, name="admin_recent_winners"),
    path("admin/user-won-items/<int:user_id>/", views.user_won_items, name="user_won_items"),
    path("admin/winner-ids/", views.winner_ids, name="winner_ids"),
    path("admin/mark_winners/", views.mark_winners, name="mark_winners"),
    path("admin/contact_winners/", views.contact_winners, name="contact_winners"),
]
