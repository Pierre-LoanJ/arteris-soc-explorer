"""Exceptions raised by the mini-EDA."""


class EdaError(Exception):
    """Base error for mini-EDA operations."""


class NotFoundError(EdaError):
    """Raised when a component or link id cannot be resolved."""


class ValidationError(EdaError):
    """Raised when an update or operation violates a basic invariant."""
