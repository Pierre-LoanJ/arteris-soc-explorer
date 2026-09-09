"""The tool registry: one table, two consumers.

``soc_explorer.adapter`` (proof 1, in-process scenarios) and
``soc_explorer.mcp_server`` (proof 2, MCP wire protocol) both read this table.
Nothing about a tool — its name, its schema, its handler, whether it mutates —
is declared twice, so the scenario results and the MCP surface cannot drift
apart.

``invoke()`` owns the response envelope, which is also declared once:

    {"ok": true,  "result": <JSON>}
    {"ok": false, "error": {"type", "code", "message", "details"?}}
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError as PydanticValidationError

from . import schemas as S
from .errors import (
    InvalidArgumentError,
    ToolError,
    UnknownToolError,
    from_eda_exception,
)
from .tools import SocExplorer


@dataclass(frozen=True)
class ToolSpec:
    name: str
    summary: str
    input_model: type[BaseModel]
    handler: Callable[[SocExplorer, Any], Any]
    mutates: bool

    @property
    def description(self) -> str:
        """What an MCP client shows to the model.

        A multi-line handler docstring documents behavior the agent needs to
        know (ranking rules, the mutation safety policy, why a missing path is
        not an error), so it wins. A one-line docstring would only restate the
        summary, so the summary is used instead.
        """
        doc = inspect.cleandoc(self.handler.__doc__ or "")
        return doc if "\n" in doc else self.summary

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def manifest_entry(self) -> dict[str, Any]:
        schema = self.input_schema()
        properties = schema.get("properties", {})
        return {
            "name": self.name,
            "description": self.summary,
            "mutates": self.mutates,
            "arity": len(properties),
            "required": sorted(schema.get("required", [])),
            "optional": sorted(set(properties) - set(schema.get("required", []))),
            "input_schema": schema,
        }


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "describe_design",
        "Overview of the loaded design: counts, kinds, clock domains, "
        "property keys, available checks. Call this first.",
        S.DescribeDesignInput,
        SocExplorer.describe_design,
        mutates=False,
    ),
    ToolSpec(
        "list_components",
        "List components, optionally filtered by kind.",
        S.ListComponentsInput,
        SocExplorer.list_components,
        mutates=False,
    ),
    ToolSpec(
        "get_component",
        "Get one component by id, with its links and bandwidth balance.",
        S.GetComponentInput,
        SocExplorer.get_component,
        mutates=False,
    ),
    ToolSpec(
        "list_links",
        "List links, optionally filtered by src and/or dst component id.",
        S.ListLinksInput,
        SocExplorer.list_links,
        mutates=False,
    ),
    ToolSpec(
        "get_link",
        "Get one link by id, flagging unresolved endpoints and clock crossings.",
        S.GetLinkInput,
        SocExplorer.get_link,
        mutates=False,
    ),
    ToolSpec(
        "search",
        "Ranked search over ids, names, kinds, endpoints and properties; each "
        "hit reports which field matched and how.",
        S.SearchInput,
        SocExplorer.search,
        mutates=False,
    ),
    ToolSpec(
        "get_neighbors",
        "Direct peers of a component, following link direction.",
        S.GetNeighborsInput,
        SocExplorer.get_neighbors,
        mutates=False,
    ),
    ToolSpec(
        "find_path",
        "Shortest directed path between two components, with latency sum and "
        "bandwidth bottleneck.",
        S.FindPathInput,
        SocExplorer.find_path,
        mutates=False,
    ),
    ToolSpec(
        "validate_design",
        "Run consistency checks (topology, clock domains, bandwidth, source "
        "duplicates) and return a structured verdict.",
        S.ValidateDesignInput,
        SocExplorer.validate_design,
        mutates=False,
    ),
    ToolSpec(
        "update_property",
        "Change one property. Previews by default (persist=false): returns the "
        "diff and the validation impact without touching the file.",
        S.UpdatePropertyInput,
        SocExplorer.update_property,
        mutates=True,
    ),
    ToolSpec(
        "set_link_endpoint",
        "Retarget a link's src or dst to an existing component; the only "
        "structural edit exposed, same preview-and-validate policy.",
        S.SetLinkEndpointInput,
        SocExplorer.set_link_endpoint,
        mutates=True,
    ),
    ToolSpec(
        "export_report",
        "Short design report as text, markdown or json.",
        S.ExportReportInput,
        SocExplorer.export_report,
        mutates=False,
    ),
)

TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


def list_tools() -> list[dict[str, Any]]:
    """Adapter-contract view: ``{name, description, mutates}`` plus schema info."""
    return [spec.manifest_entry() for spec in TOOL_SPECS]


def invoke(explorer: SocExplorer, tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Validate arguments, run the tool, and wrap the outcome in the envelope.

    Every failure path is funnelled here so no exception can ever reach a
    caller as a traceback: an unknown tool, a bad argument, a missing element
    and an internal bug all come back as ``ok: false`` with a stable code.
    """
    spec = TOOLS_BY_NAME.get(tool_name)
    if spec is None:
        return _failure(
            UnknownToolError(
                f"Unknown tool: {tool_name!r}",
                available_tools=sorted(TOOLS_BY_NAME),
            )
        )
    try:
        payload = spec.input_model.model_validate(arguments or {})
    except PydanticValidationError as exc:
        return _failure(
            InvalidArgumentError(
                f"Invalid arguments for {tool_name!r}: "
                + "; ".join(_describe_violation(err) for err in exc.errors()),
                tool=tool_name,
                violations=[
                    {"field": ".".join(str(p) for p in err["loc"]) or "<root>", "problem": err["msg"]}
                    for err in exc.errors()
                ],
                expected_schema=spec.input_schema(),
            )
        )
    try:
        result = spec.handler(explorer, payload)
    except Exception as exc:  # noqa: BLE001 - translated, never leaked raw
        return _failure(from_eda_exception(exc))
    return {"ok": True, "result": result}


def _describe_violation(err: dict[str, Any]) -> str:
    field = ".".join(str(part) for part in err["loc"]) or "<root>"
    return f"{field}: {err['msg']}"


def _failure(error: ToolError) -> dict[str, Any]:
    return {"ok": False, "error": error.to_payload()}
