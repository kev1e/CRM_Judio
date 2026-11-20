"""Errors raised by domain services. Transport layers translate them; services never return HTTP."""


class DomainError(Exception):
    """A business rule refused the operation. `code` is stable and machine-readable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PermissionDeniedError(DomainError):
    """The actor is not allowed to perform the operation."""

    def __init__(self, message: str = "Permission denied.") -> None:
        super().__init__("permission_denied", message)
