class DomainException(Exception):
    pass


class ValidationError(DomainException):
    pass


class AuthenticationError(DomainException):
    pass


class AuthorizationError(DomainException):
    pass


class NotFoundError(DomainException):
    pass


class RateLimitExceeded(DomainException):
    pass


class InternalError(DomainException):
    pass
