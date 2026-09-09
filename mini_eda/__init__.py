"""Minimal local EDA simulator for the interview exercise."""

from .api import MiniEda
from .exceptions import EdaError, NotFoundError, ValidationError

__all__ = ["MiniEda", "EdaError", "NotFoundError", "ValidationError"]
__version__ = "0.1.0"
