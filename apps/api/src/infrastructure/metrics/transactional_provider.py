"""Transaction-aware metrics for database-backed operations."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from src.domain.services.metrics_provider import MetricsProvider


class TransactionalMetricsProvider(MetricsProvider):
    """Publish audit counts only after the owning database transaction commits."""

    def __init__(self, session: AsyncSession, provider: MetricsProvider):
        self._session = session.sync_session
        self._provider = provider
        self._audit_events: dict[SessionTransaction, list[str]] = {}
        event.listen(self._session, "after_commit", self._after_commit)
        event.listen(self._session, "after_transaction_end", self._after_transaction_end)

    def track_auth_operation(
        self, operation: str, status: str, duration: float | None = None
    ) -> None:
        self._provider.track_auth_operation(operation, status, duration=duration)

    def track_audit_event(self, event_type: str) -> None:
        transaction = self._session.get_nested_transaction() or self._session.get_transaction()
        if transaction is None:
            raise RuntimeError("Audit metrics require an active database transaction")
        self._audit_events.setdefault(transaction, []).append(event_type)

    def _after_commit(self, session: Session) -> None:
        transaction = session.get_nested_transaction() or session.get_transaction()
        if transaction is None:
            return
        event_types = self._audit_events.pop(transaction, [])
        if transaction.parent is not None:
            # Releasing a savepoint is not durable until its outer transaction commits.
            self._audit_events.setdefault(transaction.parent, []).extend(event_types)
        else:
            for event_type in event_types:
                self._provider.track_audit_event(event_type)

    def _after_transaction_end(self, session: Session, transaction: SessionTransaction) -> None:
        # Rollback and close must discard counts before this session can be reused.
        self._audit_events.pop(transaction, None)
