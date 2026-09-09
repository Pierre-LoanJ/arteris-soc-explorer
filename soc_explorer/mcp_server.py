"""MCP server — proof 2 (protocol surface).

Run it over stdio:

    python -m soc_explorer.mcp_server [--design data/designs/orion_soc.json]

The server owns no tool logic. It reads ``soc_explorer.registry`` and
translates between MCP types and our response envelope, so anything an MCP
host sees is exactly what the required scenarios measure in-process.

Two protocol details worth knowing:

- a **tool failure** (missing id, bad argument, refused mutation) is returned
  as ``CallToolResult(is_error=True)`` with our structured payload, *not* as a
  JSON-RPC error: the model is supposed to read it and retry differently,
  which is why our errors carry ``code``, ``details`` and ``did_you_mean``;
- every tool declares the same ``outputSchema`` — the envelope — so a client
  can rely on one shape, and ``annotations.readOnlyHint`` tells a host which
  tools mutate (built from the registry's ``mutates`` flag, never restated).

Written against the MCP Python SDK 2.x API (``on_list_tools`` /
``on_call_tool`` callbacks; 1.x used decorators).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import anyio
import mcp.types as types
from mcp.server import NotificationOptions, Server, ServerRequestContext
from mcp.server.stdio import stdio_server

from .registry import TOOL_SPECS, invoke
from .tools import DEFAULT_DESIGN, SocExplorer

SERVER_NAME = "soc-explorer"
SERVER_VERSION = "0.1.0"

INSTRUCTIONS = """\
Tools to explore and carefully edit a SoC design (components, links, properties).

Suggested workflow:
1. `describe_design` — inventory, available property keys and check names.
2. `validate_design` — what is actually wrong; each issue carries a stable
   `code` and the name of the `check` that produced it.
3. `search` / `get_component` / `get_link` / `get_neighbors` / `find_path` —
   investigate. Search hits are ranked and say which field matched, so an
   exact id (score 1.0) is distinguishable from an incidental substring.
4. `update_property` / `set_link_endpoint` — edit. Both preview by default
   (`persist=false`): you get the diff plus the issues the change would create
   or resolve. Re-send with `persist=true` once the preview is what you want.

Every result is `{"ok": true, "result": ...}` or `{"ok": false, "error":
{"type", "code", "message", "details"}}`. Branch on `error.code`
(NOT_FOUND, INVALID_ARGUMENT, UNKNOWN_TOOL, UNSAFE_MUTATION, INTERNAL_ERROR);
`details.did_you_mean` often holds the id you meant.\
"""

#: Uniform result contract, published as every tool's ``outputSchema``.
ENVELOPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean", "description": "False when the tool refused or failed."},
        "result": {"description": "Tool-specific payload, present when ok is true."},
        "error": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "code": {
                    "type": "string",
                    "enum": [
                        "NOT_FOUND",
                        "INVALID_ARGUMENT",
                        "UNKNOWN_TOOL",
                        "UNSAFE_MUTATION",
                        "INTERNAL_ERROR",
                    ],
                },
                "message": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["type", "code", "message"],
        },
    },
    "required": ["ok"],
}


def _mcp_tool(spec: Any) -> types.Tool:
    return types.Tool(
        name=spec.name,
        title=spec.name.replace("_", " ").title(),
        description=spec.description,
        inputSchema=spec.input_schema(),
        outputSchema=ENVELOPE_SCHEMA,
        annotations=types.ToolAnnotations(
            readOnlyHint=not spec.mutates,
            # A mutating tool only writes when explicitly asked to persist,
            # and it always leaves a .bak.json copy behind.
            destructiveHint=spec.mutates,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )


def build_server(design_path: str | Path | None = None) -> Server:
    """Wire the registry into an MCP server bound to one design file."""
    explorer = SocExplorer(design_path or DEFAULT_DESIGN)

    async def on_list_tools(
        _ctx: ServerRequestContext[Any],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[_mcp_tool(spec) for spec in TOOL_SPECS])

    async def on_call_tool(
        _ctx: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        envelope = invoke(explorer, params.name, params.arguments)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=_render(envelope))],
            structuredContent=envelope,
            isError=not envelope["ok"],
        )

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        title="SoC Design Explorer",
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def _render(envelope: dict[str, Any]) -> str:
    """Human/LLM-readable text block beside the structured payload.

    ``export_report`` already returns prose, so it is passed through instead of
    being wrapped in JSON quotes — the text channel is what a model reads.
    """
    if envelope.get("ok") and isinstance(envelope.get("result"), str):
        return envelope["result"]
    return json.dumps(envelope, indent=2, ensure_ascii=False, default=str)


async def serve(design_path: str | Path | None = None) -> None:
    server = build_server(design_path)
    options = server.create_initialization_options(NotificationOptions())
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


def main() -> int:
    parser = argparse.ArgumentParser(description="SoC Design Explorer MCP server (stdio)")
    parser.add_argument(
        "--design",
        default=str(DEFAULT_DESIGN),
        help="Path to the design JSON (default: data/designs/orion_soc.json)",
    )
    args = parser.parse_args()
    anyio.run(serve, args.design)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
