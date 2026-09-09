"""Pydantic input models — one per tool.

They are the single source of truth for three things at once:

1. **validation** (a bad argument becomes a clean ``INVALID_ARGUMENT``, never a
   ``KeyError`` or a ``TypeError`` escaping to the agent);
2. **the MCP ``inputSchema``**, obtained for free via ``model_json_schema()``;
3. **the documentation the agent reads** — every ``Field(description=...)`` is
   what an LLM sees when choosing a tool, so descriptions are written for a
   reader who knows nothing about the design.

``extra="forbid"`` is deliberate: a misspelled argument fails loudly instead of
being silently ignored, which is the difference between an agent that
self-corrects and one that quietly does the wrong thing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Severity = Literal["error", "warning", "info"]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DescribeDesignInput(ToolInput):
    """No arguments: the entry point an agent calls first."""


class ListComponentsInput(ToolInput):
    kind: str | None = Field(
        default=None,
        description="Filter by component kind, e.g. 'initiator', 'router', "
        "'target', 'observer'. Omit to list every component.",
    )
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum rows returned.")


class GetComponentInput(ToolInput):
    component_id: str = Field(
        min_length=1,
        description="Exact component id (not its display name). Use search to "
        "resolve a name into an id.",
    )


class ListLinksInput(ToolInput):
    src: str | None = Field(default=None, description="Keep only links whose src is this component id.")
    dst: str | None = Field(default=None, description="Keep only links whose dst is this component id.")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum rows returned.")


class GetLinkInput(ToolInput):
    link_id: str = Field(min_length=1, description="Exact link id, e.g. 'L1'.")


class SearchInput(ToolInput):
    query: str = Field(
        min_length=1,
        description="Text to look for in ids, display names, kinds, link "
        "endpoints and property values.",
    )
    types: Literal["all", "component", "link"] = Field(
        default="all", description="Restrict results to components or links."
    )
    case_sensitive: bool = Field(
        default=False,
        description="Off by default: 'sram' must find the component whose "
        "display name is 'SRAM_L2'.",
    )
    search_properties: bool = Field(
        default=True,
        description="Also match property keys and values, e.g. 'AXI4' or 'cd_noc'.",
    )
    limit: int = Field(default=25, ge=1, le=200, description="Maximum hits returned.")


class GetNeighborsInput(ToolInput):
    component_id: str = Field(min_length=1, description="Component whose direct peers you want.")
    direction: Literal["out", "in", "both"] = Field(
        default="both",
        description="'out' follows links where the component is src, 'in' where it is dst.",
    )


class FindPathInput(ToolInput):
    src: str = Field(min_length=1, description="Start component id.")
    dst: str = Field(min_length=1, description="Destination component id.")
    max_hops: int = Field(default=8, ge=1, le=20, description="Give up beyond this many links.")


class ValidateDesignInput(ToolInput):
    checks: list[str] | None = Field(
        default=None,
        description="Subset of check names to run (see describe_design."
        "checks_available). Omit to run them all.",
    )
    min_severity: Severity = Field(
        default="info",
        description="Lowest severity to report: 'error' only, 'warning' and "
        "above, or 'info' (everything).",
    )


class UpdatePropertyInput(ToolInput):
    element_id: str = Field(min_length=1, description="Id of the component or link to modify.")
    prop_path: str = Field(
        min_length=1,
        description="Dotted path inside the element's 'properties' object, "
        "e.g. 'qos' or 'bandwidth_mbps'. Structural fields (id, src, dst, "
        "kind) are not reachable and cannot be changed.",
    )
    value: JsonValue = Field(description="New JSON value to assign.")
    persist: bool = Field(
        default=False,
        description="False (default) previews the change: you get the diff and "
        "the validation impact, and the design file is left untouched. Set "
        "True only when the preview is what you want.",
    )
    force: bool = Field(
        default=False,
        description="Persist even if the change introduces new error-severity "
        "validation issues. Without it such a write is refused.",
    )


class SetLinkEndpointInput(ToolInput):
    link_id: str = Field(min_length=1, description="Link to retarget, e.g. 'L7'.")
    role: Literal["src", "dst"] = Field(
        description="Which end of the link to move: 'src' (origin) or 'dst' (destination)."
    )
    component_id: str = Field(
        min_length=1,
        description="Existing component id to point at. A non-existent id is "
        "refused, since that is exactly the defect this repairs.",
    )
    persist: bool = Field(
        default=False,
        description="False (default) previews the change and leaves the file untouched.",
    )
    force: bool = Field(
        default=False,
        description="Persist even if the change introduces new error-severity issues.",
    )


class ExportReportInput(ToolInput):
    format: Literal["text", "json", "markdown"] = Field(
        default="text", description="Rendering of the report."
    )
