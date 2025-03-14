import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)


class TimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Define thresholds for logging
        self.warning_threshold = getattr(settings, "REQUEST_TIMING_WARNING_THRESHOLD", 0.5)  # 500ms
        self.critical_threshold = getattr(settings, "REQUEST_TIMING_CRITICAL_THRESHOLD", 2.0)  # 2s
        # Track paths to exclude from logging (static, media, admin)
        self.exclude_paths = ["/static/", "/media/", "/admin/jsi18n/"]

    def __call__(self, request):
        # Skip timing for excluded paths
        path = request.path
        for exclude in self.exclude_paths:
            if exclude in path:
                return self.get_response(request)

        # Start timing
        start_time = time.time()

        # Process the request
        response = self.get_response(request)

        # Calculate duration
        duration = time.time() - start_time

        # Add duration header for debugging
        response["X-Request-Duration"] = f"{duration:.4f}"

        # Skip logging for very fast responses if not in debug mode
        if not settings.DEBUG and duration < 0.1:
            return response

        # Different log levels based on duration
        if duration > self.critical_threshold:
            logger.error(f"CRITICAL: Request to {path} took {duration:.4f}s")
        elif duration > self.warning_threshold:
            logger.warning(f"SLOW: Request to {path} took {duration:.4f}s")
        elif settings.DEBUG:
            # Only log normal requests in debug mode
            logger.info(f"Request to {path} took {duration:.4f}s")

        return response
