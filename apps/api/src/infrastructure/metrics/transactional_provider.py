"""Transaction-aware metrics for database-backed operations."""

from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from src.domain.services.metrics_provider import MetricsProvider


class _TransactionCommitCallbacks:

    def __init__(self, session: Session):
        self._session = session
        self._callbacks: dict[SessionTransaction, list[Callable[[], None]]] = {}
        self._publishing = False
        event.listen(self._session, "after_commit", self._after_commit)
        event.listen(self._session, "after_transaction_end", self._after_transaction_end)

    def add(self, callback: Callable[[], None]) -> None:
        if self._publishing:
            # A repository commit callback must not defer its metric a second time.
            callback()
            return
        transaction = self._session.get_nested_transaction() or self._session.get_transaction()
        if transaction is None:
            raise RuntimeError("Audit metrics require an active database transaction")
        self._callbacks.setdefault(transaction, []).append(callback)

    def _after_commit(self, session: Session) -> None:
        transaction = session.get_nested_transaction() or session.get_transaction()
        if transaction is None:
            return
        callbacks = self._callbacks.pop(transaction, [])
        if transaction.parent is not None:
            # Releasing a savepoint is not durable until its outer transaction commits.
            self._callbacks.setdefault(transaction.parent, []).extend(callbacks)
        else:
            self._publishing = True
            try:
                for callback in callbacks:
                    callback()
            finally:
                self._publishing = False

    def _after_transaction_end(self, session: Session, transaction: SessionTransaction) -> None:
        # Rollback and close must discard counts before this session can be reused.
        self._callbacks.pop(transaction, None)


def defer_until_commit(session: AsyncSession, callback: Callable[[], None]) -> None:
    """Run a callback only when its owning transaction is durably committed."""
    sync_session = session.sync_session
    key = "audit_transaction_commit_callbacks"
    if key not in sync_session.info:
        sync_session.info[key] = _TransactionCommitCallbacks(sync_session)
    sync_session.info[key].add(callback)


class TransactionalMetricsProvider(MetricsProvider):
    """Publish audit counts only after the owning database transaction commits."""

    def __init__(self, session: AsyncSession, provider: MetricsProvider):
        self._session = session
        self._provider = provider

    def track_auth_operation(
        self, operation: str, status: str, duration: float | None = None
    ) -> None:
        self._provider.track_auth_operation(operation, status, duration=duration)

    def track_audit_event(self, event_type: str) -> None:
        defer_until_commit(self._session, lambda: self._provider.track_audit_event(event_type))
