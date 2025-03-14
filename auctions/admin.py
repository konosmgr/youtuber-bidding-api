from django.contrib import admin
from django.utils import timezone
from .models import Category, Item, ItemImage, Bid, User, LoginAttempt, BidAttempt, Message

class ItemImageInline(admin.TabularInline):
    model = ItemImage
    extra = 1

class BidInline(admin.TabularInline):
    model = Bid
    extra = 1
    can_delete = True
    can_add = True

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "current_price", "end_date", "is_active", "get_winner")
    list_filter = ("category", "is_active", "winner_notified", "end_date")
    search_fields = ("title", "description")
    readonly_fields = ("get_winner_info",)
    inlines = [ItemImageInline, BidInline]
    fieldsets = (
        ("Basic Information", {"fields": ("title", "category", "description", "youtube_url")}),
        ("Pricing", {"fields": ("starting_price", "current_price")}),
        ("Dates", {"fields": ("start_date", "end_date")}),
        ("Status", {"fields": ("is_active",)}),
        ("Winner Information", {"fields": ("winner", "winner_notified", "winner_contacted", "get_winner_info")}),
    )
    
    def get_winner(self, obj):
        if obj.end_date > timezone.now():
            return "Auction still active"
        if not obj.bids.exists():
            return "No bids"
        if obj.winner:
            return f"{obj.winner.email} (${obj.current_price})"
        
        # If winner not set but auction ended
        highest_bid = obj.bids.order_by('-amount').first()
        if highest_bid:
            return f"{highest_bid.user.email} (not yet marked)"
        return "No winner"
    get_winner.short_description = "Winner"
    
    def get_winner_info(self, obj):
        if not obj.winner and not obj.bids.exists():
            return "No bids on this auction"
        if not obj.winner and obj.bids.exists():
            highest_bid = obj.bids.order_by('-amount').first()
            return f"Highest bidder: {highest_bid.user.email} (${highest_bid.amount})"
        if obj.winner:
            return f"Winner: {obj.winner.email} - Notified: {'Yes' if obj.winner_notified else 'No'} - Contacted: {obj.winner_contacted or 'No'}"
        return "No winner information available"
    get_winner_info.short_description = "Winner Status"
    
    # Only keeping contact_winners action
    actions = ["contact_winners"]
    
    def contact_winners(self, request, queryset):
        winners_contacted = 0
        for item in queryset:
            if item.winner and not item.winner_notified:
                # Send email notification
                self.send_winner_notification(item)
                
                # Create message in system
                Message.objects.create(
                    sender=request.user,
                    receiver=item.winner,
                    content=f"Congratulations! You've won the auction for {item.title} with a bid of ${item.current_price}. Please respond to arrange payment and shipping details."
                )
                
                item.winner_notified = True
                item.winner_contacted = timezone.now()
                item.save()
                winners_contacted += 1
        
        self.message_user(request, f"Contacted {winners_contacted} auction winners.")
    contact_winners.short_description = "Contact selected auction winners"
    
    def send_winner_notification(self, item):
        """Send email notification to auction winner"""
        from django.core.mail import send_mail
        from django.conf import settings
        
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
            
    def save_model(self, request, obj, form, change):
        if not obj.id or not obj.current_price:
            obj.current_price = obj.starting_price
        super().save_model(request, obj, form, change)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "created_at")
    search_fields = ("name", "code")
    ordering = ("name",)


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ("item", "get_username", "amount", "created_at")
    list_filter = ("created_at", "item")
    search_fields = ("user__email", "user__username", "item__title")
    
    def get_username(self, obj):
        return obj.user.username if obj.user else "Unknown"
    get_username.short_description = 'User'
    get_username.admin_order_field = 'user__username'


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'is_staff', 'email_verified')
    search_fields = ('username', 'email', 'nickname', 'full_name')
    list_filter = ('is_staff', 'is_active', 'email_verified')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'content_preview', 'created_at', 'is_read')
    list_filter = ('is_read', 'created_at')
    search_fields = ('content', 'sender__username', 'receiver__username')
    
    def content_preview(self, obj):
        return obj.content[:50] + ('...' if len(obj.content) > 50 else '')
    content_preview.short_description = 'Content'


# Register remaining models
admin.site.register(LoginAttempt)
admin.site.register(BidAttempt)
admin.site.register(ItemImage)