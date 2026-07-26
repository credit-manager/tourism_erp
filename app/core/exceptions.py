"""
Domain exceptions. Services raise these; a single exception handler
(registered once in app/main.py) maps them to HTTP responses.
This keeps services framework-agnostic (no HTTPException inside business logic).
"""


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class DuplicateError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class JournalImbalanceError(DomainError):
    """Raised when a double-entry posting's debits != credits. Must never happen
    if LedgerService is used correctly — this is a structural safety net."""
    pass


class PermissionDeniedError(DomainError):
    pass
