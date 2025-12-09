import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings

logger = logging.getLogger("app.security_headers")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security-related HTTP response headers.

    This middleware adds the following security headers to all responses:
    - X-Frame-Options: Prevents clickjacking attacks
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-XSS-Protection: Disables legacy XSS filter (modern browsers use CSP)
    - Referrer-Policy: Controls referrer information in requests
    - Content-Security-Policy: Restricts resource loading for API responses
    - Strict-Transport-Security (HSTS): Forces HTTPS connections (when enabled)
    """

    def __init__(self, app, enable_hsts: bool | None = None):
        super().__init__(app)
        self.enable_hsts = enable_hsts if enable_hsts is not None else settings.enable_hsts

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # X-Frame-Options: Prevent clickjacking by not allowing the page to be framed
        response.headers["X-Frame-Options"] = "DENY"

        # X-Content-Type-Options: Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-XSS-Protection: Disable the legacy XSS filter
        # Modern browsers should rely on CSP instead
        response.headers["X-XSS-Protection"] = "0"

        # Referrer-Policy: Control how much referrer information is included
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content-Security-Policy: For API responses, restrict everything
        # This is appropriate for JSON APIs that don't serve HTML/JS/CSS
        response.headers["Content-Security-Policy"] = "default-src 'none'"

        # Strict-Transport-Security (HSTS): Force HTTPS for 1 year
        # Only enable when the app is behind HTTPS (production)
        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
