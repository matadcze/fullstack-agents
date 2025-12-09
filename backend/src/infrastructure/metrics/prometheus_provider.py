"""Prometheus metrics provider implementation."""

from src.core.metrics import audit_events_total, auth_operation_duration, auth_operations_total
from src.domain.services.metrics_provider import MetricsProvider


class PrometheusMetricsProvider(MetricsProvider):
    """Prometheus implementation of metrics provider."""

    def track_auth_operation(
        self, operation: str, status: str, duration: float | None = None
    ) -> None:
        """Track authentication operation metrics."""
        auth_operations_total.labels(operation=operation, status=status).inc()
        if duration is not None:
            auth_operation_duration.labels(operation=operation).observe(duration)

    def track_audit_event(self, event_type: str) -> None:
        """Track audit event creation."""
        audit_events_total.labels(event_type=event_type).inc()
