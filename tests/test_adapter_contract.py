"""The contract the scenario runner and any MCP host depend on."""

from __future__ import annotations

import json

import pytest

from soc_explorer.adapter import SocExplorerAdapter, get_adapter
from soc_explorer.errors import ERROR_CODES
from soc_explorer.registry import TOOL_SPECS


def test_get_adapter_defaults_to_orion() -> None:
    adapter = get_adapter()
    assert adapter.explorer.design.name == "orion_soc"


def test_manifest_entries_are_complete_and_serialisable(adapter: SocExplorerAdapter) -> None:
    tools = adapter.list_tools()
    assert len(tools) == len(TOOL_SPECS)
    for tool in tools:
        assert set(tool) >= {"name", "description", "mutates", "arity", "required", "input_schema"}
        assert tool["description"].strip()
        assert isinstance(tool["mutates"], bool)
        assert tool["arity"] == len(tool["input_schema"].get("properties", {}))
    json.dumps(tools)  # must survive the manifest artifact


def test_only_the_two_edit_tools_declare_mutation(adapter: SocExplorerAdapter) -> None:
    mutating = {tool["name"] for tool in adapter.list_tools() if tool["mutates"]}
    assert mutating == {"update_property", "set_link_endpoint"}


def test_success_envelope(adapter: SocExplorerAdapter) -> None:
    response = adapter.call("list_components", {})
    assert response["ok"] is True
    assert set(response) == {"ok", "result"}


def test_unknown_tool_lists_the_alternatives(adapter: SocExplorerAdapter) -> None:
    response = adapter.call("teleport", {})
    assert response["ok"] is False
    assert response["error"]["code"] == "UNKNOWN_TOOL"
    assert "list_components" in response["error"]["details"]["available_tools"]


def test_unknown_argument_is_rejected_not_ignored(adapter: SocExplorerAdapter) -> None:
    response = adapter.call("get_component", {"componentId": "cpu0"})
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    fields = {violation["field"] for violation in response["error"]["details"]["violations"]}
    assert {"component_id", "componentId"} & fields


def test_missing_required_argument(adapter: SocExplorerAdapter) -> None:
    assert adapter.call("get_component", {})["error"]["code"] == "INVALID_ARGUMENT"


def test_arguments_may_be_omitted_entirely(adapter: SocExplorerAdapter) -> None:
    assert adapter.call("describe_design", None)["ok"] is True


@pytest.mark.parametrize("code", ERROR_CODES)
def test_error_codes_are_documented(code: str) -> None:
    assert code.isupper() and " " not in code


def test_no_tool_raises_instead_of_returning_the_envelope(adapter: SocExplorerAdapter) -> None:
    """Every declared tool is callable with empty arguments without exploding."""
    for tool in adapter.list_tools():
        response = adapter.call(tool["name"], {})
        assert response["ok"] in (True, False)
        if not response["ok"]:
            assert response["error"]["code"] in ERROR_CODES
