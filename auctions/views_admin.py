@api_view(['GET'])
@permission_classes([IsAdminUser])
def recent_winners(request):
    """Get recent auction winners for admin dashboard"""
    # Get items that have ended with a winner set
    recent_winners = Item.objects.filter(
        winner__isnull=False,
        end_date__lt=timezone.now()
    ).order_by('-end_date')[:10]  # Last 10 winners
    
    result = []
    for item in recent_winners:
        result.append({
            'item': {
                'id': item.id,
                'title': item.title,
                'current_price': float(item.current_price),
                'end_date': item.end_date
            },
            'user': {
                'id': item.winner.id,
                'email': item.winner.email,
                'nickname': item.winner.nickname or '',
            }
        })
    
    return Response(result)