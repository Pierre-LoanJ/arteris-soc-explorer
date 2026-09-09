"""Candidate tool adapter — proof 1 (in-process required scenarios).

Thin on purpose. Everything the runner exercises (tool names, argument
validation, result shapes, error codes) lives in ``soc_explorer.registry`` and
``soc_explorer.tools``, which is what ``soc_explorer.mcp_server`` serves over
MCP. This file only satisfies the runner's contract:

- ``list_tools()`` -> list of ``{name, description, mutates, ...}``
- ``call(tool, args)`` -> ``{"ok": True, "result": ...}``
                        | ``{"ok": False, "error": {"type", "code", "message"}}``

so scenario results describe the real MCP contract rather than a parallel
implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import invoke, list_tools
from .tools import DEFAULT_DESIGN, SocExplorer


class SocExplorerAdapter:
    """Adapter over the shared tool registry."""

    def __init__(self, design_path: str | Path | None = None) -> None:
        self.explorer = SocExplorer(design_path or DEFAULT_DESIGN)

    def list_tools(self) -> list[dict[str, Any]]:
        return list_tools()

    def call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return invoke(self.explorer, tool_name, arguments)


def get_adapter(design_path: str | Path | None = None) -> SocExplorerAdapter:
    """Entry point used by ``scripts/run_required_scenarios.py``."""
    return SocExplorerAdapter(design_path)
