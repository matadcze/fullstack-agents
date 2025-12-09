import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logging import get_correlation_id, log_json, set_correlation_id

logger = logging.getLogger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        correlation_id = (
            request.headers.get("X-Correlation-ID") or get_correlation_id() or str(uuid.uuid4())
        )

        set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id

        log_json(
            logger,
            event="request_started",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )

        response: Response | None = None

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_json(
                logger,
                event="request_failed",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                duration_ms=round(duration_ms, 2),
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_json(
                logger,
                event="request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code if response else None,
                duration_ms=round(duration_ms, 2),
            )
            response.headers["X-Correlation-ID"] = correlation_id
            return response
