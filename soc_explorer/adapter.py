"""Candidate tool adapter.

Replace ``TemplateAdapter`` wiring with calls into your MCP tool layer
(or call your tool functions directly). The required-scenarios runner imports
``get_adapter`` from this module.

Contract
--------
- ``list_tools()`` -> list of {name, description, mutates: bool}
- ``call(tool_name, arguments)`` -> dict with at least:
    {"ok": bool, "result": Any} on success
    {"ok": false, "error": {"type": str, "message": str}} on failure

Keep results JSON-serializable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_eda import MiniEda, NotFoundError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESIGN = ROOT / "data" / "designs" / "orion_soc.json"


class TemplateAdapter:
    """Baseline adapter over MiniEda.

    This proves the measurement pipeline. For your submission, prefer routing
    through the same functions your MCP server exposes so scenarios exercise
    *your* contracts (errors, schemas, validation behavior).
    """

    def __init__(self, design_path: Path | None = None) -> None:
        self.eda = MiniEda(design_path or DEFAULT_DESIGN)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_components",
                "description": "List components, optionally filtered by kind",
                "mutates": False,
            },
            {
                "name": "get_component",
                "description": "Get one component by id",
                "mutates": False,
            },
            {
                "name": "search",
                "description": "Search components/links by substring",
                "mutates": False,
            },
            {
                "name": "validate_design",
                "description": "Run consistency checks",
                "mutates": False,
            },
            {
                "name": "update_property",
                "description": "Update a property on a component or link",
                "mutates": True,
            },
            {
                "name": "export_report",
                "description": "Export a short design report",
                "mutates": False,
            },
        ]

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._dispatch(tool_name, arguments)
            return {"ok": True, "result": result}
        except NotFoundError as exc:
            return {
                "ok": False,
                "error": {"type": "NotFoundError", "message": str(exc)},
            }
        except ValidationError as exc:
            return {
                "ok": False,
                "error": {"type": "ValidationError", "message": str(exc)},
            }
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors to harness
            return {
                "ok": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }

    def _dispatch(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "list_components":
            comps = self.eda.list_components(kind=arguments.get("kind"))
            return [c.to_dict() for c in comps]
        if tool_name == "get_component":
            return self.eda.get_component(arguments["component_id"]).to_dict()
        if tool_name == "search":
            return self.eda.search(arguments.get("query", ""))
        if tool_name == "validate_design":
            return [i.to_dict() for i in self.eda.validate()]
        if tool_name == "update_property":
            return self.eda.update_property(
                arguments["element_id"],
                arguments["prop_path"],
                arguments["value"],
                persist=bool(arguments.get("persist", True)),
            )
        if tool_name == "export_report":
            return self.eda.export_report(arguments.get("format", "text"))
        raise ValidationError(f"Unknown tool: {tool_name}")


def get_adapter() -> TemplateAdapter:
    """Entry point used by ``scripts/run_required_scenarios.py``."""
    return TemplateAdapter()
