import json
import logging
from contextvars import ContextVar
from typing import Any, Dict, Optional

correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


def set_correlation_id(correlation_id: str) -> None:
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    correlation_id_var.set(None)


def log_json(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    payload: Dict[str, Any] = {"event": event, **fields}
    correlation_id = get_correlation_id()
    if correlation_id:
        payload["correlation_id"] = correlation_id

    logger.log(level, json.dumps(payload, default=str))
