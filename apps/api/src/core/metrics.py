from prometheus_client import Counter, Gauge, Histogram


def _get_or_create_counter(name, description, labelnames=None):

    try:
        return Counter(name, description, labelnames or [])
    except ValueError:
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names.keys()):
            if hasattr(collector, "_name") and collector._name == name:
                return collector
        raise


def _get_or_create_gauge(name, description, labelnames=None):

    try:
        return Gauge(name, description, labelnames or [])
    except ValueError:
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names.keys()):
            if hasattr(collector, "_name") and collector._name == name:
                return collector
        raise


def _get_or_create_histogram(name, description, labelnames=None, buckets=None):

    try:
        kwargs = {"labelnames": labelnames or []}
        if buckets:
            kwargs["buckets"] = buckets
        return Histogram(name, description, **kwargs)
    except ValueError:
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names.keys()):
            if hasattr(collector, "_name") and collector._name == name:
                return collector
        raise


http_requests_total = _get_or_create_counter(
    "http_requests_total",
    "Total HTTP requests processed",
    ["method", "path", "status"],
)

http_errors_total = _get_or_create_counter(
    "http_errors_total",
    "Total HTTP requests returning error status codes",
    ["method", "path", "status"],
)

http_request_duration_seconds = _get_or_create_histogram(
    "http_request_duration_seconds",
    "Duration of HTTP requests in seconds",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


auth_requests_total = _get_or_create_counter(
    "auth_requests",
    "Total number of authentication requests",
    ["endpoint", "status"],
)

auth_failures_total = _get_or_create_counter(
    "auth_failures",
    "Total number of failed authentication attempts",
    ["reason"],
)

auth_operations_total = _get_or_create_counter(
    "auth_operations",
    "Total number of auth operations",
    ["operation", "status"],
)

auth_operation_duration = _get_or_create_histogram(
    "auth_operation_duration_seconds",
    "Duration of auth operations in seconds",
    ["operation"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0),
)

active_sessions = _get_or_create_gauge(
    "active_sessions",
    "Number of currently active user sessions",
)

database_query_duration = _get_or_create_histogram(
    "database_query_duration_seconds",
    "Duration of database queries in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

database_connections = _get_or_create_gauge(
    "database_connections",
    "Number of active database connections",
)

database_errors_total = _get_or_create_counter(
    "database_errors",
    "Total number of database errors",
    ["error_type"],
)

cache_operations_total = _get_or_create_counter(
    "cache_operations",
    "Total number of cache operations",
    ["operation", "status"],
)

cache_hit_rate = _get_or_create_gauge(
    "cache_hit_rate",
    "Cache hit rate (percentage)",
)

audit_events_total = _get_or_create_counter(
    "audit_events",
    "Total number of audit events",
    ["event_type"],
)

api_errors_total = _get_or_create_counter(
    "api_errors",
    "Total number of API errors",
    ["endpoint", "error_code", "status_code"],
)

rate_limit_exceeded_total = _get_or_create_counter(
    "rate_limit_exceeded",
    "Total number of rate limit violations",
    ["endpoint"],
)
