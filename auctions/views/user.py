"""
User management views for the auctions app.
"""

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from auctions.models import User
from auctions.serializers import UserSerializer

# Setup logger
logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for user management"""

    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action in ["retrieve", "update", "partial_update"]:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        # Users can only see their own profile
        if not self.request.user.is_staff:
            return User.objects.filter(id=self.request.user.id)
        return User.objects.all()

    @action(detail=False, methods=["get"])
    def me(self, request):
        """Get current user profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """Update user profile including notification preferences"""
        user = request.user
        logger.info(f"Updating profile for user: {user.email}")
        logger.info(f"Received data: {request.data}")

        # Create a serializer with the user and data
        serializer = self.get_serializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            # Save the updated user
            serializer.save()
            logger.info(f"Profile updated successfully: {serializer.data}")
            return Response(serializer.data)

        logger.info(f"Profile update validation errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([AllowAny])
def check_nickname_availability(request):
    """Check if a nickname is available"""
    nickname = request.query_params.get("nickname")
    if not nickname:
        return Response(
            {"detail": "Nickname parameter is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if nickname exists
    exists = User.objects.filter(nickname=nickname).exists()
    return Response({"available": not exists})
