from django.db.models import Count, Sum, Avg, F, ExpressionWrapper, fields, Q
from django.db.models.functions import TruncDay, TruncHour, TruncMonth
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import User, Item, Bid, LoginAttempt, BidAttempt, Category


@api_view(['GET'])
@permission_classes([IsAdminUser])
def analytics_overview(request):
    """Provides top-level metrics for the dashboard"""
    
    # Calculate time range based on query param
    time_range = request.query_params.get('timeRange', '30days')
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
    total_revenue = Item.objects.filter(
        end_date__lt=timezone.now(),
        end_date__gte=date_from
    ).aggregate(
        revenue=Sum('current_price')
    )['revenue'] or 0
    
    # Calculate conversion rate (bids divided by page views)
    # Note: This is a placeholder. You would need to implement page view tracking
    conversion_rate = 0  # To be calculated if you have page view data
    
    return Response({
        'total_users': total_users,
        'new_users': new_users,
        'total_items': total_items,
        'active_items': active_items,
        'total_bids': total_bids,
        'total_revenue': total_revenue,
        'conversion_rate': conversion_rate
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def user_metrics(request):
    """Provides user-related metrics"""
    
    time_range = request.query_params.get('timeRange', '30days')
    date_from = calculate_date_range(time_range)
    
    # Daily new user registrations
    registrations = User.objects.filter(
        date_joined__gte=date_from
    ).annotate(
        date=TruncDay('date_joined')
    ).values('date').annotate(
        count=Count('id')
    ).order_by('date')
    
    # Login activity by hour
    logins_by_hour = LoginAttempt.objects.filter(
        timestamp__gte=date_from,
        success=True
    ).annotate(
        hour=TruncHour('timestamp')
    ).values('hour').annotate(
        count=Count('id')
    ).order_by('hour')
    
    return Response({
        'registrations': registrations,
        'logins_by_hour': logins_by_hour
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def auction_metrics(request):
    """Provides auction and bidding metrics"""
    
    time_range = request.query_params.get('timeRange', '30days')
    date_from = calculate_date_range(time_range)
    
    # Bids over time
    bids_over_time = Bid.objects.filter(
        created_at__gte=date_from
    ).annotate(
        date=TruncDay('created_at')
    ).values('date').annotate(
        count=Count('id')
    ).order_by('date')
    
    # Category distribution
    category_distribution = Category.objects.annotate(
        item_count=Count('item')
    ).values('name', 'item_count')
    
    # Revenue by category
    revenue_by_category = Item.objects.filter(
        end_date__lt=timezone.now(),
        end_date__gte=date_from
    ).values('category__name').annotate(
        revenue=Sum('current_price')
    ).order_by('-revenue')
    
    # Monthly sales
    monthly_sales = Item.objects.filter(
        end_date__lt=timezone.now(),
        end_date__gte=date_from
    ).annotate(
        month=TruncMonth('end_date')
    ).values('month').annotate(
        sales=Sum('current_price')
    ).order_by('month')
    
    return Response({
        'bids_over_time': bids_over_time,
        'category_distribution': category_distribution,
        'revenue_by_category': revenue_by_category,
        'monthly_sales': monthly_sales
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def top_items(request):
    """Returns top performing items by bids"""
    
    time_range = request.query_params.get('timeRange', '30days')
    date_from = calculate_date_range(time_range)
    
    # Get top items by bid count
    top_items = Item.objects.annotate(
        bid_count=Count('bids', filter=Q(bids__created_at__gte=date_from))
    ).order_by('-bid_count')[:10]
    
    # Format response data
    result = []
    for item in top_items:
        result.append({
            'id': item.id,
            'title': item.title,
            'category': item.category.name,
            'bids': item.bid_count,
            'current_price': float(item.current_price),
            # You'd add view count here if you have that data
            'views': 0
        })
    
    return Response(result)


def calculate_date_range(time_range):
    """Helper function to calculate the start date based on time range"""
    now = timezone.now()
    
    if time_range == '7days':
        return now - timedelta(days=7)
    elif time_range == '30days':
        return now - timedelta(days=30)
    elif time_range == '90days':
        return now - timedelta(days=90)
    elif time_range == 'year':
        return now - timedelta(days=365)
    else:
        # Default to 30 days
        return now - timedelta(days=30)