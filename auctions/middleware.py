import time
import logging

logger = logging.getLogger(__name__)

class TimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        duration = time.time() - start_time
        response['X-Request-Duration'] = str(duration)
        
        # Log requests that take more than 500ms
        if duration > 0.5:
            logger.warning(f"Slow request: {request.path} took {duration:.2f}s")
        else:
            logger.info(f"Request: {request.path} took {duration:.2f}s")
            
        return response