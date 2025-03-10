from .models import Item, Category, Bid, ItemImage, Message
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import User, Bid, Item, Category, ItemImage
from .profanity_filter import profanity_filter

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user details including notification preferences"""
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'nickname', 'full_name', 
                  'profile_picture', 'email_verified', 'is_staff',
                  'outbid_notifications_enabled', 'win_notifications_enabled']
        read_only_fields = ['id', 'email_verified', 'is_staff']
        
    def validate_nickname(self, value):
        """Validate that nickname is unique and does not contain profanity"""
        if not value:
            return value
            
        # Skip validation if nickname hasn't changed (for updates)
        if self.instance and self.instance.nickname == value:
            return value
            
        # Check for profanity
        if profanity_filter.contains_profanity(value):
            raise serializers.ValidationError("Your nickname contains inappropriate language. Please choose a different nickname.")
            
        # Check uniqueness
        if User.objects.filter(nickname=value).exists():
            raise serializers.ValidationError("This nickname is already taken. Please choose another one.")
            
        return value
        
class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    captcha_response = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'password_confirm', 'nickname', 'full_name', 'captcha_response']
        extra_kwargs = {
            'nickname': {'required': False},
            'full_name': {'required': False},
            'username': {'required': False}
        }

    
    def validate_nickname(self, value):
        """Validate that nickname does not contain profanity and is unique"""
        if not value:
            return value
            
        # Check for profanity
        if profanity_filter.contains_profanity(value):
            raise serializers.ValidationError("Your nickname contains inappropriate language. Please choose a different nickname.")
            
        # Check uniqueness
        if User.objects.filter(nickname=value).exists():
            raise serializers.ValidationError("This nickname is already taken. Please choose another one.")
            
        return value    

    def validate(self, attrs):
        # Check that passwords match
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        
        # Remove captcha_response from attrs as it's not a user field
        attrs.pop('captcha_response', None)
        
        # Generate username from email if not provided
        if not attrs.get('username'):
            email_username = attrs['email'].split('@')[0]
            # Ensure username is unique by adding numbers if needed
            username = email_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{email_username}{counter}"
                counter += 1
            attrs['username'] = username
        
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password_confirm', None)
        user = User.objects.create_user(**validated_data)
        return user

class LoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    captcha_response = serializers.CharField(write_only=True, required=False)  # Optional for frequent users

class GoogleAuthSerializer(serializers.Serializer):
    """Serializer for Google authentication"""
    token = serializers.CharField(required=True)
    
# Update your BidSerializer to work with the User model
class BidSerializer(serializers.ModelSerializer):
    user_nickname = serializers.CharField(source='user.nickname', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = Bid
        fields = ["id", "user", "user_nickname", "user_email", "amount", "created_at"]
        read_only_fields = ["id", "created_at", "user_nickname", "user_email"]

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "code"]


class ItemImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemImage
        fields = ["id", "image", "order"]

    def get_image(self, obj):
        # Return just the relative path without the domain
        if obj.image:
            return obj.image.url
        return None

class ItemSerializer(serializers.ModelSerializer):
    images = ItemImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    bids = BidSerializer(many=True, read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=Category.objects.all(), write_only=True
    )

    winner = UserSerializer(read_only=True)

    class Meta:
        model = Item
        fields = [
            "id",
            "title",
            "description",
            "category",
            "category_id",
            "starting_price",
            "current_price",
            "start_date",
            "end_date",
            "is_active",
            "images",
            "bids",
            "created_at",
            "youtube_url",
            "winner",
            "winner_notified",
            "winner_contacted",
        ]
        read_only_fields = ["current_price", "created_at"]

    def create(self, validated_data):
        # Set current_price to starting_price for new items
        validated_data["current_price"] = validated_data["starting_price"]
        return super().create(validated_data)


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    receiver_username = serializers.CharField(source='receiver.username', read_only=True, allow_null=True)
    
    class Meta:
        model = Message
        fields = ['id', 'sender', 'sender_username', 'receiver', 'receiver_username', 
                  'content', 'created_at', 'is_read']
        read_only_fields = ['id', 'created_at', 'is_read', 'sender_username', 'receiver_username']
        extra_kwargs = {
            'receiver': {'required': False, 'allow_null': True},
        }