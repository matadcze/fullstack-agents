"""Metrics provider interface for tracking application metrics."""

from abc import ABC, abstractmethod


class MetricsProvider(ABC):
    """Abstract base class for metrics providers."""

    @abstractmethod
    def track_auth_operation(
        self, operation: str, status: str, duration: float | None = None
    ) -> None:
        """Track authentication operation metrics.

        Args:
            operation: The operation name (e.g., 'login', 'register')
            status: The operation status ('success' or 'error')
            duration: Optional operation duration in seconds
        """
        pass

    @abstractmethod
    def track_audit_event(self, event_type: str) -> None:
        """Track audit event creation.

        Args:
            event_type: The type of audit event
        """
        pass
