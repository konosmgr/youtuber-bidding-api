"""
Message related views for the auctions app.
"""

import logging
import traceback

from django.db import models
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from auctions.models import Message, User
from auctions.serializers import MessageSerializer, UserSerializer

# Setup logger
logger = logging.getLogger(__name__)


class MessageViewSet(viewsets.ModelViewSet):
    """ViewSet for user-admin messaging"""

    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            # Admins can see all messages
            return Message.objects.all()
        else:
            # Regular users can only see their conversations
            return Message.objects.filter(models.Q(sender=user) | models.Q(receiver=user))

    def create(self, request, *args, **kwargs):
        """Handle message creation with improved debugging and error handling"""
        try:
            user = request.user
            logger.info(
                f"Message creation request from user: {user.username} (is_staff: {user.is_staff})"
            )
            logger.info(f"Request data: {request.data}")

            # Prepare data for serialization
            message_data = request.data.copy()

            # Always set the sender to the current user
            message_data["sender"] = user.id

            # Handle receiver properly based on user type
            if user.is_staff and "receiver" in request.data and request.data["receiver"]:
                # Admin sending to specific user - use the provided receiver
                receiver_id = request.data["receiver"]
                logger.info(f"Admin sending message to user ID: {receiver_id}")

                # Verify the receiver exists
                try:
                    receiver = User.objects.get(id=receiver_id)
                    logger.info(f"Verified receiver exists: {receiver.username}")
                except User.DoesNotExist:
                    return Response(
                        {"detail": f"Receiver with ID {receiver_id} does not exist."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            elif not user.is_staff:
                # Regular user sending to admin - set receiver to null
                message_data["receiver"] = None
                logger.info(f"User sending message to admin (receiver=null)")

            logger.info(f"Final message data for serializer: {message_data}")

            # Create the serializer with our prepared data
            serializer = self.get_serializer(data=message_data)

            if not serializer.is_valid():
                logger.info(f"Serializer validation errors: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Save the message
            message = serializer.save()
            logger.info(f"Message created successfully: {message.id}")

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating message: {str(e)}")
            logger.error(traceback.format_exc())
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def my_conversations(self, request):
        """Get conversations for current user"""
        user = request.user
        if user.is_staff:
            # For admins, get all unique users who have sent messages
            senders = User.objects.filter(sent_messages__receiver__isnull=True).distinct()

            # Get latest message for each sender
            conversations = []
            for sender in senders:
                # Get all messages between this user and admin
                all_messages = Message.objects.filter(
                    models.Q(sender=sender, receiver__isnull=True)
                    | models.Q(sender__is_staff=True, receiver=sender)
                ).order_by("-created_at")

                # Get the latest message separately
                latest_message = all_messages.first()

                if latest_message:
                    # Count unread messages in a separate query
                    unread_count = Message.objects.filter(
                        sender=sender, receiver__isnull=True, is_read=False
                    ).count()

                    conversations.append(
                        {
                            "user": UserSerializer(sender).data,
                            "latest_message": MessageSerializer(latest_message).data,
                            "unread_count": unread_count,
                        }
                    )

            return Response(conversations)
        else:
            # For regular users, get their conversation with admin
            all_messages = Message.objects.filter(
                models.Q(sender=user, receiver__isnull=True)
                | models.Q(sender__is_staff=True, receiver=user)
            ).order_by("-created_at")

            # Get latest 10 messages
            messages = all_messages[:10]

            # Count unread in a separate query
            unread_count = Message.objects.filter(
                sender__is_staff=True, receiver=user, is_read=False
            ).count()

            return Response(
                {
                    "messages": MessageSerializer(messages, many=True).data,
                    "unread_count": unread_count,
                }
            )

    @action(detail=False, methods=["get"])
    def admin_chat(self, request):
        """Get messages between current user and admin"""
        user = request.user

        # Mark messages as read
        if not user.is_staff:
            Message.objects.filter(sender__is_staff=True, receiver=user, is_read=False).update(
                is_read=True
            )

        # Get messages
        messages = Message.objects.filter(
            models.Q(sender=user, receiver__isnull=True)
            | models.Q(sender__is_staff=True, receiver=user)
        ).order_by("created_at")

        return Response(MessageSerializer(messages, many=True).data)

    @action(detail=False, methods=["get"])
    def user_chat(self, request, user_id=None):
        """Get messages between admin and a specific user"""
        if not request.user.is_staff:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            user_id = self.kwargs.get("user_id") or request.query_params.get("user_id")
            user = User.objects.get(id=user_id)

            # Mark messages as read
            Message.objects.filter(sender=user, receiver__isnull=True, is_read=False).update(
                is_read=True
            )

            # Get messages
            messages = Message.objects.filter(
                models.Q(sender=user, receiver__isnull=True)
                | models.Q(sender__is_staff=True, receiver=user)
            ).order_by("created_at")

            return Response(MessageSerializer(messages, many=True).data)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def debug_send_message(request):
    """Debug endpoint for sending test messages"""
    user = request.user
    text = request.data.get("text", "Test message")

    try:
        # Create a message
        if user.is_staff:
            # Admin sending to a user
            receiver_id = request.data.get("receiver")
            if not receiver_id:
                return Response(
                    {"detail": "Receiver ID is required for admin messages"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                receiver = User.objects.get(id=receiver_id)
                message = Message.objects.create(sender=user, receiver=receiver, text=text)
            except User.DoesNotExist:
                return Response(
                    {"detail": f"User with ID {receiver_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            # Regular user sending to admin
            message = Message.objects.create(sender=user, receiver=None, text=text)

        return Response(
            {"detail": f"Message sent successfully with ID {message.id}"},
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.error(f"Error in debug_send_message: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {"detail": f"Error sending message: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
