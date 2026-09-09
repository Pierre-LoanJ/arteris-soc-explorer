"""The MCP surface itself: discovery and a call over the real protocol.

The session runs on in-memory streams instead of a subprocess, so it exercises
the protocol handlers without a process launch or a plugin: ``anyio.run``
drives the coroutine from an ordinary synchronous test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from mcp.server import NotificationOptions

from soc_explorer.mcp_server import ENVELOPE_SCHEMA, build_server
from soc_explorer.registry import TOOL_SPECS


def with_session(design: Path, scenario: Callable[[ClientSession], Awaitable[Any]]) -> Any:
    """Run ``scenario`` against a live server over paired memory streams."""

    async def _main() -> Any:
        server = build_server(design)
        options = server.create_initialization_options(NotificationOptions())
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            client_read, client_write = client_streams
            server_read, server_write = server_streams
            async with anyio.create_task_group() as tg:
                tg.start_soon(lambda: server.run(server_read, server_write, options, raise_exceptions=True))
                async with ClientSession(client_read, client_write) as session:
                    await session.initialize()
                    outcome = await scenario(session)
                tg.cancel_scope.cancel()
            return outcome

    return anyio.run(_main)


def test_handshake_advertises_the_server_and_its_instructions(design_copy: Path) -> None:
    async def scenario(session: ClientSession) -> tuple[str, str]:
        result = session.initialize_result
        return result.server_info.name, result.instructions or ""

    name, instructions = with_session(design_copy, scenario)
    assert name == "soc-explorer"
    # The instructions are what an LLM reads before choosing a tool.
    assert "persist=false" in instructions
    assert "NOT_FOUND" in instructions


def test_tools_list_matches_the_registry(design_copy: Path) -> None:
    async def scenario(session: ClientSession):
        return (await session.list_tools()).tools

    tools = with_session(design_copy, scenario)
    assert [tool.name for tool in tools] == [spec.name for spec in TOOL_SPECS]
    for tool in tools:
        assert tool.description and tool.input_schema["type"] == "object"
        assert tool.output_schema == ENVELOPE_SCHEMA
        assert tool.annotations is not None
    read_only = {tool.name: tool.annotations.read_only_hint for tool in tools}
    assert read_only["search"] is True
    assert read_only["update_property"] is False
    assert read_only["set_link_endpoint"] is False


def test_call_tool_returns_structured_content(design_copy: Path) -> None:
    async def scenario(session: ClientSession):
        return await session.call_tool("get_component", {"component_id": "cpu0"})

    result = with_session(design_copy, scenario)
    assert result.is_error is False
    assert result.structured_content["ok"] is True
    assert result.structured_content["result"]["kind"] == "initiator"
    assert result.content[0].text.startswith("{")


def test_a_tool_failure_is_a_result_not_a_protocol_error(design_copy: Path) -> None:
    """An agent must be able to read the failure and retry, so isError=True
    travels with our structured payload instead of a JSON-RPC error."""

    async def scenario(session: ClientSession):
        return await session.call_tool("get_component", {"component_id": "sram_l2"})

    result = with_session(design_copy, scenario)
    assert result.is_error is True
    error = result.structured_content["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["details"]["did_you_mean"] == ["sram0"]


def test_report_text_reaches_the_model_as_prose(design_copy: Path) -> None:
    async def scenario(session: ClientSession):
        return await session.call_tool("export_report", {"format": "text"})

    result = with_session(design_copy, scenario)
    assert result.content[0].text.startswith("Design: orion_soc")


def test_mutation_over_mcp_defaults_to_a_preview(design_copy: Path) -> None:
    before = design_copy.read_text(encoding="utf-8")

    async def scenario(session: ClientSession):
        return await session.call_tool(
            "update_property", {"element_id": "cpu0", "prop_path": "qos", "value": "low"}
        )

    result = with_session(design_copy, scenario)
    assert result.structured_content["result"]["dry_run"] is True
    assert design_copy.read_text(encoding="utf-8") == before
