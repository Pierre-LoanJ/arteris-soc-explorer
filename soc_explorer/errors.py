"""Stable, agent-facing error taxonomy.

Why a dedicated module: an agent must be able to *branch* on a failure
without parsing prose. ``mini_eda`` only offers ``NotFoundError`` /
``ValidationError`` with free-text messages, so we add:

- a short, stable ``code`` (the contract an agent can rely on);
- a structured ``details`` payload (which id was missing, what was expected);
- a ``did_you_mean`` hint, because the Orion fixture contains a real
  id/display-name confusion (link ``L7`` points at ``sram_l2`` while the
  component id is ``sram0``).

The wire payload keeps ``type`` and ``message`` so it stays compatible with
the contract documented in ``soc_explorer/adapter.py``.
"""

from __future__ import annotations

import difflib
from typing import Any, Iterable

from mini_eda import exceptions as eda_exceptions


class ToolError(Exception):
    """Base class for every failure a tool reports to an agent."""

    code = "INTERNAL_ERROR"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        # Drop unset keys so payloads stay small and predictable.
        self.details = {k: v for k, v in details.items() if v not in (None, [], {})}

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": type(self).__name__,
            "code": self.code,
            "message": str(self),
        }
        if self.details:
            payload["details"] = self.details
        return payload


class NotFoundError(ToolError):
    """An element id could not be resolved in the design."""

    code = "NOT_FOUND"


class InvalidArgumentError(ToolError):
    """Arguments failed schema validation or a documented precondition."""

    code = "INVALID_ARGUMENT"


class UnknownToolError(ToolError):
    """The requested tool name is not registered."""

    code = "UNKNOWN_TOOL"


class UnsafeMutationError(ToolError):
    """A mutation was refused by the safety policy (see tools.update_property)."""

    code = "UNSAFE_MUTATION"


class InternalError(ToolError):
    """Unexpected failure; a bug in the server rather than in the request."""

    code = "INTERNAL_ERROR"


#: Codes an agent may branch on. Kept explicit so it can be asserted in tests
#: and published in the tool manifest.
ERROR_CODES = (
    NotFoundError.code,
    InvalidArgumentError.code,
    UnknownToolError.code,
    UnsafeMutationError.code,
    InternalError.code,
)


def did_you_mean(needle: str, candidates: Iterable[str], limit: int = 3) -> list[str]:
    """Best-effort id suggestions, case-insensitive.

    Handles the Orion trap directly: ``did_you_mean("sram_l2", ids)`` -> ``["sram0"]``
    is found through the substring pass, not through the fuzzy pass.
    """
    pool = list(candidates)
    lowered = needle.lower()
    substring = [c for c in pool if lowered in c.lower() or c.lower() in lowered]
    fuzzy = difflib.get_close_matches(needle, pool, n=limit, cutoff=0.6)
    ordered: list[str] = []
    for candidate in substring + fuzzy:
        if candidate != needle and candidate not in ordered:
            ordered.append(candidate)
    return ordered[:limit]


def from_eda_exception(exc: Exception) -> ToolError:
    """Translate a ``mini_eda`` exception into our taxonomy.

    Anything unexpected becomes ``InternalError`` so a crash never escapes as
    a raw traceback through the MCP surface.
    """
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, eda_exceptions.NotFoundError):
        return NotFoundError(str(exc), source="mini_eda")
    if isinstance(exc, eda_exceptions.ValidationError):
        return InvalidArgumentError(str(exc), source="mini_eda")
    return InternalError(f"{type(exc).__name__}: {exc}")
