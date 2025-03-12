from datetime import datetime
from typing import TYPE_CHECKING, List

from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager


class CustomUserManager(UserManager):
    """Custom user manager that applies password validation during user creation"""

    def _create_user(self, username, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        Apply password validation before user creation.
        """
        if not username:
            raise ValueError("The given username must be set")

        email = self.normalize_email(email)
        username = self.model.normalize_username(username)

        # Validate password if provided
        if password is not None:
            try:
                validate_password(password)
            except ValidationError as error:
                raise ValidationError({"password": error.messages})

        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractUser):
    """Extended user model for the auction system"""

    email = models.EmailField(unique=True)
    nickname = models.CharField(max_length=50, blank=True, unique=True)
    full_name = models.CharField(max_length=100, blank=True)
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=100, blank=True)
    verification_token_expires = models.DateTimeField(null=True, blank=True)
    google_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    profile_picture = models.URLField(blank=True, null=True)

    # Notification preferences
    outbid_notifications_enabled = models.BooleanField(default=True)
    win_notifications_enabled = models.BooleanField(default=True)

    # Set the custom manager
    objects = CustomUserManager()

    def __str__(self):
        return self.email or self.username

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"


class LoginAttempt(models.Model):
    """Track login attempts for rate limiting"""

    email = models.EmailField()
    ip_address = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.email} - {self.ip_address} - {'Success' if self.success else 'Failed'}"

    class Meta:
        ordering = ["-timestamp"]


class BidAttempt(models.Model):
    """Track bid attempts for rate limiting"""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user or 'Anonymous'} - {self.ip_address} - {'Success' if self.success else 'Failed'}"

    class Meta:
        ordering = ["-timestamp"]


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ItemQuerySet(models.QuerySet):
    """Custom QuerySet with optimized queries for Items"""

    def active(self):
        """Get only active auctions that haven't ended"""
        from django.utils import timezone

        return self.filter(is_active=True, end_date__gt=timezone.now())

    def ended(self):
        """Get auctions that have ended"""
        from django.utils import timezone

        return self.filter(end_date__lte=timezone.now())

    def with_bid_counts(self):
        """Annotate with bid counts for more efficient querying"""
        return self.annotate(bid_count=Count("bids", distinct=True))

    def with_first_image(self):
        """Annotate with the first image URL for efficient list views"""
        first_image = (
            ItemImage.objects.filter(item=OuterRef("pk")).order_by("order").values("image")[:1]
        )

        first_image_id = (
            ItemImage.objects.filter(item=OuterRef("pk")).order_by("order").values("id")[:1]
        )

        return self.annotate(
            first_image=Subquery(first_image), first_image_id=Subquery(first_image_id)
        )

    def by_category(self, category_code):
        """Filter by category code"""
        if not category_code:
            return self
        return self.filter(category__code=category_code)

    def with_full_relations(self):
        """Load all related data for detailed views"""
        return self.prefetch_related(
            "images",
            "bids__user",
        ).select_related("category", "winner")


class ItemManager(models.Manager):
    def get_queryset(self):
        return ItemQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def ended(self):
        return self.get_queryset().ended()

    def with_bid_counts(self):
        return self.get_queryset().with_bid_counts()

    def with_first_image(self):
        return self.get_queryset().with_first_image()


class Item(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField()
    starting_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    current_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    winner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="won_items"
    )
    winner_notified = models.BooleanField(default=False)
    winner_contacted = models.DateTimeField(null=True, blank=True)
    objects = ItemManager()

    # Add index to end_date for efficient queries of active/expired items
    class Meta:
        indexes = [
            models.Index(fields=["end_date"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["category"]),
            models.Index(fields=["end_date", "is_active"]),
        ]
        ordering = ["-created_at"]  # Default ordering

    if TYPE_CHECKING:
        bids: RelatedManager["Bid"]
        images: RelatedManager["ItemImage"]

    youtube_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Make sure current_price is set for new items
        if not self.id or not self.current_price:
            self.current_price = self.starting_price

        # Ensure winners are only assigned to ended auctions
        if self.winner and self.end_date > timezone.now():
            self.winner = None
            self.winner_notified = False
            self.winner_contacted = None

        super().save(*args, **kwargs)


class Bid(models.Model):
    item = models.ForeignKey(Item, related_name="bids", on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-amount"]

    def __str__(self):
        # return f"{user_email} bid ${self.amount} on {self.item.title}" #this made docker undefined
        return (
            f"{self.user.email if self.user else 'Unknown'} bid ${self.amount} on {self.item.title}"
        )

    def clean(self):
        if self.item.bids.exists():
            highest_bid = self.item.bids.first()  # Due to ordering = ['-amount']
            max_allowed = highest_bid.amount * 2
            if self.amount > max_allowed:
                raise ValidationError(
                    f"Bid cannot exceed {int(max_allowed)}$ (100% more than current bid)"
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_messages", null=True, blank=True
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"From {self.sender} to {self.receiver or 'Admin'} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class ItemImage(models.Model):
    item = models.ForeignKey(Item, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="images/")
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Image {self.order} for {self.item.title}"
