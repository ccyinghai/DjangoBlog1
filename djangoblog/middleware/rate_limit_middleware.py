import logging
from django.core.cache import cache
from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)

class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.rate_limit_requests = getattr(settings, 'RATE_LIMIT_REQUESTS', 100) # Default to 100 requests
        self.rate_limit_time_window = getattr(settings, 'RATE_LIMIT_TIME_WINDOW', 60) # Default to 60 seconds

    def __call__(self, request):
        # Allow admin, static, and other specific paths to bypass rate limiting
        # You can customize these paths as needed
        bypass_paths = [
            '/admin/',
            settings.STATIC_URL,
            '/ckeditor/upload/',
            '/wasabi-file-list-json/',
            '/sitemap.xml',
            '/robots.txt',
        ]
        if any(request.path.startswith(path) for path in bypass_paths):
            return self.get_response(request)

        ip_address = self.get_client_ip(request)
        if ip_address:
            cache_key = f'rate_limit:{ip_address}'
            # Atomically increment the count and set expiry if it's a new entry
            count = cache.get(cache_key, 0)
            if count == 0:
                cache.set(cache_key, 1, timeout=self.rate_limit_time_window)
            else:
                cache.incr(cache_key)

            if count >= self.rate_limit_requests:
                logger.warning(f"Rate limit exceeded for IP: {ip_address}")
                return HttpResponse("Too many requests.", status=429)
        
        response = self.get_response(request)
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
