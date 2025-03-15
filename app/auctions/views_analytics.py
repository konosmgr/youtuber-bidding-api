import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Avg, Count, ExpressionWrapper, F, Q, Sum, fields
from django.db.models.functions import TruncDay, TruncHour, TruncMonth
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import Bid, BidAttempt, Category, Item, LoginAttempt, User

# Setup logger
logger = logging.getLogger(__name__)

# Cache timeouts
ANALYTICS_CACHE_TIMEOUT = 30 * 60  # 30 minutes


@api_view(["GET"])
@permission_classes([IsAdminUser])
def analytics_overview(request):
    """Provides top-level metrics for the dashboard"""

    # Calculate time range based on query param
    time_range = request.query_params.get("timeRange", "30days")

    # Create cache key based on time range
    cache_key = f"analytics_overview_{time_range}"

    # Try to get from cache
    cached_response = cache.get(cache_key)
    if cached_response:
        logger.debug(f"Serving analytics overview from cache: {cache_key}")
        return cached_response

    # Not in cache, generate the response
    date_from = calculate_date_range(time_range)

    # Total users
    total_users = User.objects.count()
    new_users = User.objects.filter(date_joined__gte=date_from).count()

    # Total items
    total_items = Item.objects.count()
    active_items = Item.objects.filter(is_active=True).count()

    # Total bids
    total_bids = Bid.objects.filter(created_at__gte=date_from).count()

    # Total revenue (from current_price of items where end_date has passed)
    total_revenue = (
        Item.objects.filter(end_date__lt=timezone.now(), end_date__gte=date_from).aggregate(
            revenue=Sum("current_price")
        )["revenue"]
        or 0
    )

    # Calculate conversion rate (bids divided by page views)
    # Note: This is a placeholder. You would need to implement page view tracking
    conversion_rate = 0  # To be calculated if you have page view data

    response = Response(
        {
            "total_users": total_users,
            "new_users": new_users,
            "total_items": total_items,
            "active_items": active_items,
            "total_bids": total_bids,
            "total_revenue": total_revenue,
            "conversion_rate": conversion_rate,
        }
    )

    # Cache the response
    cache.set(cache_key, response, ANALYTICS_CACHE_TIMEOUT)
    logger.debug(f"Caching analytics overview: {cache_key}")

    return response


@api_view(["GET"])
@permission_classes([IsAdminUser])
def user_metrics(request):
    """Provides user-related metrics"""

    time_range = request.query_params.get("timeRange", "30days")

    # Create cache key based on time range
    cache_key = f"user_metrics_{time_range}"

    # Try to get from cache
    cached_response = cache.get(cache_key)
    if cached_response:
        logger.debug(f"Serving user metrics from cache: {cache_key}")
        return cached_response

    # Not in cache, generate the response
    date_from = calculate_date_range(time_range)

    # Get user registrations over time
    registrations = (
        User.objects.filter(date_joined__gte=date_from)
        .annotate(date=TruncDay("date_joined"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )

    # Get login attempts over time
    login_attempts = (
        LoginAttempt.objects.filter(timestamp__gte=date_from)
        .annotate(date=TruncDay("timestamp"))
        .values("date")
        .annotate(
            success_count=Count("id", filter=Q(success=True)),
            failure_count=Count("id", filter=Q(success=False)),
        )
        .order_by("date")
    )

    # User bid activity
    bid_activity = (
        Bid.objects.filter(created_at__gte=date_from)
        .values("user_id")
        .annotate(bid_count=Count("id"))
        .order_by("-bid_count")[:10]
    )

    # Get recent failed logins for security monitoring
    failed_logins = (
        LoginAttempt.objects.filter(success=False, timestamp__gte=date_from)
        .order_by("-timestamp")
        .values("ip_address", "timestamp", "username")[:20]
    )

    response = Response(
        {
            "registrations": registrations,
            "login_attempts": login_attempts,
            "bid_activity": bid_activity,
            "failed_logins": failed_logins,
        }
    )

    # Cache the response
    cache.set(cache_key, response, ANALYTICS_CACHE_TIMEOUT)
    logger.debug(f"Caching user metrics: {cache_key}")

    return response


@api_view(["GET"])
@permission_classes([IsAdminUser])
def auction_metrics(request):
    """Provides auction and bidding metrics"""

    time_range = request.query_params.get("timeRange", "30days")

    # Create cache key based on time range
    cache_key = f"auction_metrics_{time_range}"

    # Try to get from cache
    cached_response = cache.get(cache_key)
    if cached_response:
        logger.debug(f"Serving auction metrics from cache: {cache_key}")
        return cached_response

    # Not in cache, generate the response
    date_from = calculate_date_range(time_range)

    # Bids over time
    bids_over_time = (
        Bid.objects.filter(created_at__gte=date_from)
        .annotate(date=TruncDay("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )

    # Category distribution
    category_distribution = Category.objects.annotate(item_count=Count("item")).values(
        "name", "item_count"
    )

    # Revenue by category
    revenue_by_category = (
        Item.objects.filter(end_date__lt=timezone.now(), end_date__gte=date_from)
        .values("category__name")
        .annotate(revenue=Sum("current_price"))
        .order_by("-revenue")
    )

    # Monthly sales
    monthly_sales = (
        Item.objects.filter(end_date__lt=timezone.now(), end_date__gte=date_from)
        .annotate(month=TruncMonth("end_date"))
        .values("month")
        .annotate(sales=Sum("current_price"))
        .order_by("month")
    )

    response = Response(
        {
            "bids_over_time": bids_over_time,
            "category_distribution": category_distribution,
            "revenue_by_category": revenue_by_category,
            "monthly_sales": monthly_sales,
        }
    )

    # Cache the response
    cache.set(cache_key, response, ANALYTICS_CACHE_TIMEOUT)
    logger.debug(f"Caching auction metrics: {cache_key}")

    return response


@api_view(["GET"])
@permission_classes([IsAdminUser])
def top_items(request):
    """Returns top performing items by bids"""

    time_range = request.query_params.get("timeRange", "30days")

    # Create cache key based on time range
    cache_key = f"top_items_{time_range}"

    # Try to get from cache
    cached_response = cache.get(cache_key)
    if cached_response:
        logger.debug(f"Serving top items from cache: {cache_key}")
        return cached_response

    # Not in cache, generate the response
    date_from = calculate_date_range(time_range)

    # Get top items by bid count with optimized query
    top_items = (
        Item.objects.select_related("category")
        .annotate(bid_count=Count("bids", filter=Q(bids__created_at__gte=date_from)))
        .order_by("-bid_count")[:10]
    )

    # Format response data
    result = []
    for item in top_items:
        result.append(
            {
                "id": item.id,
                "title": item.title,
                "category": item.category.name,
                "bids": item.bid_count,
                "current_price": float(item.current_price),
                # You'd add view count here if you have that data
                "views": 0,
            }
        )

    response = Response(result)

    # Cache the response
    cache.set(cache_key, response, ANALYTICS_CACHE_TIMEOUT)
    logger.debug(f"Caching top items: {cache_key}")

    return response


def calculate_date_range(time_range):
    """Helper function to calculate the start date based on time range"""
    now = timezone.now()

    if time_range == "7days":
        return now - timedelta(days=7)
    elif time_range == "30days":
        return now - timedelta(days=30)
    elif time_range == "90days":
        return now - timedelta(days=90)
    elif time_range == "year":
        return now - timedelta(days=365)
    else:
        # Default to 30 days
        return now - timedelta(days=30)
