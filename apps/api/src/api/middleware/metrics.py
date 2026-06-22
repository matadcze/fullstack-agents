import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.metrics import http_errors_total, http_request_duration_seconds, http_requests_total


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.perf_counter() - start
            status_code = response.status_code if response else 500
            method = request.method
            path = request.url.path

            http_requests_total.labels(method=method, path=path, status=str(status_code)).inc()
            http_request_duration_seconds.labels(method=method, path=path).observe(duration)
            if status_code >= 400:
                http_errors_total.labels(method=method, path=path, status=str(status_code)).inc()
