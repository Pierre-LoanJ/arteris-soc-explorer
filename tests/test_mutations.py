"""The write path: what a preview promises, and what a refusal protects."""

from __future__ import annotations

import json
from pathlib import Path

from soc_explorer.adapter import SocExplorerAdapter


def props(path: Path, element_id: str) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for section in ("components", "links"):
        for element in raw[section]:
            if element["id"] == element_id:
                return element
    raise AssertionError(f"{element_id} not in file")


def test_preview_is_the_default(adapter: SocExplorerAdapter, design_copy: Path) -> None:
    response = adapter.call(
        "update_property", {"element_id": "cpu0", "prop_path": "qos", "value": "low"}
    )
    result = response["result"]
    assert result["dry_run"] is True and result["persisted"] is False
    assert result["change"] == {
        "field": "properties.qos",
        "prop_path": "qos",
        "operation": "updated",
        "old_value": "high",
        "new_value": "low",
        "old_type": "str",
        "new_type": "str",
        "type_changed": False,
    }
    # The returned element shows the *would-be* state...
    assert result["element"]["properties"]["qos"] == "low"
    # ...while neither the file nor the loaded design moved.
    assert props(design_copy, "cpu0")["properties"]["qos"] == "high"
    assert adapter.call("get_component", {"component_id": "cpu0"})["result"]["properties"]["qos"] == "high"
    assert not design_copy.with_suffix(".bak.json").exists()


def test_persist_writes_and_leaves_a_backup(adapter: SocExplorerAdapter, design_copy: Path) -> None:
    result = adapter.call(
        "update_property",
        {"element_id": "cpu0", "prop_path": "qos", "value": "low", "persist": True},
    )["result"]
    assert result["persisted"] is True
    assert props(design_copy, "cpu0")["properties"]["qos"] == "low"
    backup = design_copy.with_suffix(".bak.json")
    assert backup.exists()
    assert json.loads(backup.read_text())["components"][0]["properties"]["qos"] == "high"


def test_new_property_is_reported_as_created(adapter: SocExplorerAdapter) -> None:
    change = adapter.call(
        "update_property", {"element_id": "cpu0", "prop_path": "owner", "value": "team-noc"}
    )["result"]["change"]
    assert change["operation"] == "created"
    assert change["old_value"] is None and change["old_type"] is None


def test_same_value_is_reported_as_unchanged(adapter: SocExplorerAdapter) -> None:
    change = adapter.call(
        "update_property", {"element_id": "cpu0", "prop_path": "qos", "value": "high"}
    )["result"]["change"]
    assert change["operation"] == "unchanged"


def test_type_change_is_surfaced(adapter: SocExplorerAdapter) -> None:
    change = adapter.call(
        "update_property", {"element_id": "L1", "prop_path": "bandwidth_mbps", "value": "12800"}
    )["result"]["change"]
    assert change["type_changed"] is True
    assert (change["old_type"], change["new_type"]) == ("int", "str")


def test_dangerous_write_is_refused_and_rolled_back(
    adapter: SocExplorerAdapter, design_copy: Path
) -> None:
    error = adapter.call(
        "update_property",
        {"element_id": "L1", "prop_path": "bandwidth_mbps", "value": -5, "persist": True},
    )["error"]
    assert error["code"] == "UNSAFE_MUTATION"
    assert error["details"]["blocking_issues"][0]["code"] == "NON_POSITIVE_BANDWIDTH"
    assert error["details"]["retry_with"] == {"force": True}
    # Nothing written, nothing left dirty in memory.
    assert props(design_copy, "L1")["properties"]["bandwidth_mbps"] == 12800
    assert adapter.call("get_link", {"link_id": "L1"})["result"]["properties"]["bandwidth_mbps"] == 12800
    assert adapter.call("validate_design", {"min_severity": "error"})["result"]["issue_count"] == 2


def test_force_lets_an_operator_override(adapter: SocExplorerAdapter, design_copy: Path) -> None:
    result = adapter.call(
        "update_property",
        {
            "element_id": "L1",
            "prop_path": "bandwidth_mbps",
            "value": -5,
            "persist": True,
            "force": True,
        },
    )["result"]
    assert result["forced"] is True and result["persisted"] is True
    assert props(design_copy, "L1")["properties"]["bandwidth_mbps"] == -5


def test_a_refused_preview_does_not_need_force_to_be_seen(adapter: SocExplorerAdapter) -> None:
    """A preview that would break the design is still refused — by design.

    The blocking issues travel in the error payload, so the caller learns why
    without the tool having to pretend the edit is acceptable.
    """
    response = adapter.call(
        "update_property", {"element_id": "L1", "prop_path": "bandwidth_mbps", "value": -5}
    )
    assert response["ok"] is False
    assert len(response["error"]["details"]["blocking_issues"]) == 1


def test_invalid_property_path_is_rejected_by_mini_eda(adapter: SocExplorerAdapter) -> None:
    error = adapter.call(
        "update_property", {"element_id": "cpu0", "prop_path": "../etc", "value": 1}
    )["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["details"]["source"] == "mini_eda"


def test_structural_fields_are_out_of_reach(adapter: SocExplorerAdapter) -> None:
    """prop_path is relative to `properties`, so this cannot retarget a link."""
    result = adapter.call(
        "update_property", {"element_id": "L7", "prop_path": "dst", "value": "sram0"}
    )["result"]
    assert result["element"]["dst"] == "sram_l2"  # untouched
    assert result["element"]["properties"]["dst"] == "sram0"  # a new property
    assert result["validation"]["resolved_issues"] == []


def test_update_on_unknown_element_suggests_alternatives(adapter: SocExplorerAdapter) -> None:
    error = adapter.call(
        "update_property", {"element_id": "sram_l2", "prop_path": "qos", "value": "low"}
    )["error"]
    assert error["code"] == "NOT_FOUND"
    assert "sram0" in error["details"]["did_you_mean"]


def test_set_link_endpoint_previews_the_repair(adapter: SocExplorerAdapter, design_copy: Path) -> None:
    result = adapter.call(
        "set_link_endpoint", {"link_id": "L7", "role": "dst", "component_id": "sram0"}
    )["result"]
    assert result["dry_run"] is True
    assert result["change"] == {
        "field": "dst",
        "operation": "updated",
        "old_value": "sram_l2",
        "new_value": "sram0",
        "old_type": "str",
        "new_type": "str",
        "type_changed": False,
    }
    resolved = {issue["code"] for issue in result["validation"]["resolved_issues"]}
    assert resolved == {"DANGLING_LINK_ENDPOINT", "UNCONNECTED_COMPONENT"}
    # The preview also surfaces the *side effect*: the repaired link crosses
    # clock domains, which nobody asked about.
    assert [issue["code"] for issue in result["validation"]["new_issues"]] == ["CLOCK_DOMAIN_CROSSING"]
    assert props(design_copy, "L7")["dst"] == "sram_l2"


def test_set_link_endpoint_applies_and_clears_the_errors(
    adapter: SocExplorerAdapter, design_copy: Path
) -> None:
    result = adapter.call(
        "set_link_endpoint",
        {"link_id": "L7", "role": "dst", "component_id": "sram0", "persist": True},
    )["result"]
    assert result["persisted"] is True
    assert result["backup_path"].endswith(".bak.json")
    assert props(design_copy, "L7")["dst"] == "sram0"
    assert adapter.call("validate_design", {"min_severity": "error"})["result"]["issue_count"] == 0
    # The topology index was rebuilt, so paths now reflect the repair.
    assert adapter.call("find_path", {"src": "cpu0", "dst": "sram0"})["result"]["found"] is True


def test_set_link_endpoint_refuses_to_create_a_dangling_endpoint(adapter: SocExplorerAdapter) -> None:
    error = adapter.call(
        "set_link_endpoint", {"link_id": "L7", "role": "dst", "component_id": "sram_l2"}
    )["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["details"]["did_you_mean"] == ["sram0"]


def test_set_link_endpoint_rejects_a_bogus_role(adapter: SocExplorerAdapter) -> None:
    error = adapter.call(
        "set_link_endpoint", {"link_id": "L7", "role": "middle", "component_id": "sram0"}
    )["error"]
    assert error["code"] == "INVALID_ARGUMENT"
