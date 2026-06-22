from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.middleware import (
    MetricsMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from src.api.schemas import ErrorDetail, ErrorResponse
from src.api.v1 import agents, audit, auth, health
from src.core.config import settings
from src.core.logging import configure_logging, get_correlation_id
from src.domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DomainException,
    NotFoundError,
    RateLimitExceeded,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        description="Production-ready FastAPI + Next.js template with authentication and audit logging",
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/")
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "running",
            "docs": "/api/docs",
        }

    @app.get("/metrics")
    async def metrics():

        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException):
        status_code = status.HTTP_400_BAD_REQUEST
        correlation_id = getattr(request.state, "correlation_id", None) or get_correlation_id()

        if isinstance(exc, AuthenticationError):
            status_code = status.HTTP_401_UNAUTHORIZED
        elif isinstance(exc, AuthorizationError):
            status_code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, NotFoundError):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, RateLimitExceeded):
            status_code = status.HTTP_429_TOO_MANY_REQUESTS

        error_detail = ErrorDetail(
            code=exc.__class__.__name__,
            message=str(exc),
            details={},
            correlation_id=correlation_id,
        )
        response = JSONResponse(
            status_code=status_code,
            content=ErrorResponse(error=error_detail).model_dump(),
        )
        if correlation_id:
            response.headers["X-Correlation-ID"] = correlation_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        correlation_id = getattr(request.state, "correlation_id", None) or get_correlation_id()
        error_detail = ErrorDetail(
            code="ValidationError",
            message="Request validation failed",
            details={"errors": exc.errors()},
            correlation_id=correlation_id,
        )
        response = JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(error=error_detail).model_dump(),
        )
        if correlation_id:
            response.headers["X-Correlation-ID"] = correlation_id
        return response

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        correlation_id = getattr(request.state, "correlation_id", None) or get_correlation_id()
        error_detail = ErrorDetail(
            code="InternalServerError",
            message="An unexpected error occurred",
            details={} if not settings.debug else {"error": str(exc)},
            correlation_id=correlation_id,
        )
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error=error_detail).model_dump(),
        )
        if correlation_id:
            response.headers["X-Correlation-ID"] = correlation_id
        return response

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app)

    return app


app = create_app()
