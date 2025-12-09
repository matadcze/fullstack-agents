import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def configure_logging() -> None:
    """Configure application-wide JSON logging with correlation IDs."""
    if logging.getLogger().handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    logging.basicConfig(level=logging.INFO, handlers=[handler])

    # Apply JSON handler to common server loggers (uvicorn, etc.)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False


def set_correlation_id(correlation_id: str) -> None:
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    correlation_id_var.set(None)


def log_json(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    payload: Dict[str, Any] = {"event": event, **fields}
    logger.log(level, payload)


class JsonFormatter(logging.Formatter):
    """Simple JSON formatter that adds correlation IDs and timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = get_correlation_id()
        base: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }

        if isinstance(record.msg, dict):
            base.update(record.msg)
        else:
            base["message"] = record.getMessage()

        if correlation_id and "correlation_id" not in base:
            base["correlation_id"] = correlation_id

        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            base["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(base, default=str)
