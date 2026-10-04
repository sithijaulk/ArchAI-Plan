from __future__ import annotations


class ELIAError(Exception):
    """Expected ELIA validation or planning failure with an API-safe code."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class InfeasibleLayout(Exception):
    """A validly evaluated design that cannot satisfy its constraints."""

    def __init__(self, reason: str, violations: list[str]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.violations = violations
