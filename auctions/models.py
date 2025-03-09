from datetime import datetime
from typing import TYPE_CHECKING, List

from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models  # added the bellow for user login and auth
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
    nickname = models.CharField(
        max_length=50, blank=True, unique=True
    )  # Added unique=True
    full_name = models.CharField(max_length=100, blank=True)
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=100, blank=True)
    verification_token_expires = models.DateTimeField(null=True, blank=True)
    google_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    profile_picture = models.URLField(blank=True, null=True)

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

    if TYPE_CHECKING:
        bids: RelatedManager["Bid"]
        images: RelatedManager["ItemImage"]

    youtube_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):  # This is line 100
        # Make sure the following lines are properly indented
        if not self.id or not self.current_price:  # This is line 102
            self.current_price = self.starting_price
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
        return f"{self.user.email if self.user else 'Unknown'} bid ${self.amount} on {self.item.title}"

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
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_messages"
    )
    receiver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_messages",
        null=True,
        blank=True,
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

    def save(self, *args, **kwargs):
        # Check if this is a new image being saved (not in database yet)
        if self.image and hasattr(self.image, "file") and not self.id:
            from django.core.files.base import ContentFile

            # Read the file content
            file_content = self.image.read()

            # Create file name (keep original or generate a new one if needed)
            file_name = self.image.name

            # Reset file pointer
            self.image.seek(0)

            # Replace with ContentFile to ensure proper handling
            self.image = ContentFile(file_content, name=file_name)

        # Call the original save method
        super().save(*args, **kwargs)

    def get_image_url(self):
        if self.image and hasattr(self.image, "url"):
            return self.image.url
        return None
