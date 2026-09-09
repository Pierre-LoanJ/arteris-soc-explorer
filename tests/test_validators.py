"""Consistency checks: what they find on Orion, and what they refuse to guess."""

from __future__ import annotations

from pathlib import Path

from soc_explorer.adapter import SocExplorerAdapter
from soc_explorer.tools import SocExplorer
from soc_explorer.validators import CHECK_NAMES, CheckContext, run_checks


def codes(issues: list[dict]) -> set[str]:
    return {issue["code"] for issue in issues}


def test_orion_is_not_clean_even_though_mini_eda_says_so(explorer: SocExplorer) -> None:
    """The headline result: the built-in checks report nothing, ours report 11."""
    assert explorer.eda.validate() == []
    verdict = run_checks(explorer._check_context())
    assert verdict["issue_count"] == 11
    assert verdict["by_severity"] == {"error": 2, "warning": 4, "info": 5}
    assert codes(verdict["issues"]) == {
        "DANGLING_LINK_ENDPOINT",
        "UNCONNECTED_COMPONENT",
        "BANDWIDTH_OVERSUBSCRIPTION",
        "MISSING_CLOCK_DOMAIN",
        "SELF_LOOP",
        "CLOCK_DOMAIN_CROSSING",
    }


def test_every_issue_names_the_check_that_produced_it(adapter: SocExplorerAdapter) -> None:
    issues = adapter.call("validate_design", {})["result"]["issues"]
    assert all(issue["check"] in CHECK_NAMES for issue in issues)


def test_severity_filter(adapter: SocExplorerAdapter) -> None:
    errors = adapter.call("validate_design", {"min_severity": "error"})["result"]
    assert errors["issue_count"] == 2
    assert codes(errors["issues"]) == {"DANGLING_LINK_ENDPOINT", "UNCONNECTED_COMPONENT"}
    warnings = adapter.call("validate_design", {"min_severity": "warning"})["result"]
    assert warnings["issue_count"] == 6


def test_checks_can_be_selected(adapter: SocExplorerAdapter) -> None:
    verdict = adapter.call("validate_design", {"checks": ["self_loop"]})["result"]
    assert verdict["checks_run"] == ["self_loop"]
    assert [issue["element_id"] for issue in verdict["issues"]] == ["L_loop"]


def test_unknown_check_is_a_usable_error(adapter: SocExplorerAdapter) -> None:
    error = adapter.call("validate_design", {"checks": ["bandwidth"]})["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["details"]["unknown_checks"] == ["bandwidth"]
    assert "bandwidth_oversubscription" in error["details"]["available_checks"]


def test_dangling_endpoint_details_are_actionable(adapter: SocExplorerAdapter) -> None:
    issue = next(
        issue
        for issue in adapter.call("validate_design", {"checks": ["dangling_link_endpoint"]})["result"]["issues"]
    )
    assert issue["element_id"] == "L7"
    assert issue["details"] == {
        "role": "dst",
        "missing_id": "sram_l2",
        "did_you_mean": ["sram0"],
    }


def test_oversubscription_payload_is_auditable(adapter: SocExplorerAdapter) -> None:
    issues = adapter.call("validate_design", {"checks": ["bandwidth_oversubscription"]})["result"]["issues"]
    r0 = next(issue for issue in issues if issue["element_id"] == "r0")
    assert r0["details"]["ingress_mbps"] == 39628
    assert r0["details"]["egress_mbps"] == 36200
    # The numbers must be traceable to named links, not appear out of nowhere.
    assert set(r0["details"]["ingress_links"]) == {"L1", "L2", "L3", "L8", "L_loop"}
    assert set(r0["details"]["egress_links"]) == {"L4", "L5", "L_loop"}


def test_builtin_check_is_delegated_not_reimplemented(design_writer) -> None:
    path = design_writer(
        "bad_bandwidth",
        {
            "name": "tiny",
            "components": [
                {"id": "a", "kind": "initiator", "name": "A", "properties": {"clock_domain": "cd"}},
                {"id": "b", "kind": "target", "name": "B", "properties": {"clock_domain": "cd"}},
            ],
            "links": [{"id": "l1", "src": "a", "dst": "b", "properties": {"bandwidth_mbps": -1}}],
        },
    )
    explorer = SocExplorer(path)
    issues = run_checks(explorer._check_context(), checks=["builtin_bandwidth"])["issues"]
    assert codes(issues) == {"NON_POSITIVE_BANDWIDTH"}
    assert issues[0]["details"]["delegated_to"] == "mini_eda.MiniEda.validate"


def test_duplicate_ids_are_caught_in_the_file(design_writer) -> None:
    """mini_eda cannot see this: load() collapses duplicates into one dict entry."""
    path = design_writer(
        "dupes",
        {
            "name": "tiny",
            "components": [
                {"id": "a", "kind": "initiator", "name": "A1", "properties": {}},
                {"id": "a", "kind": "target", "name": "A2", "properties": {}},
            ],
            "links": [],
        },
    )
    explorer = SocExplorer(path)
    assert len(explorer.design.components) == 1  # the evidence is gone in memory
    issues = run_checks(explorer._check_context(), checks=["duplicate_id_in_source"])["issues"]
    assert codes(issues) == {"DUPLICATE_COMPONENT_ID"}
    assert issues[0]["details"]["occurrences"] == 2


def test_protocol_mismatch_fires_when_it_should(design_writer) -> None:
    """It reports nothing on Orion; prove the rule still works."""
    path = design_writer(
        "mismatch",
        {
            "name": "tiny",
            "components": [
                {"id": "a", "kind": "initiator", "name": "A", "properties": {"protocol": "AXI4"}},
                {"id": "b", "kind": "target", "name": "B", "properties": {"protocol": "APB"}},
            ],
            "links": [{"id": "l1", "src": "a", "dst": "b", "properties": {"protocol": "AXI4"}}],
        },
    )
    issues = run_checks(SocExplorer(path)._check_context(), checks=["protocol_mismatch"])["issues"]
    assert [issue["details"]["component_id"] for issue in issues] == ["b"]


def test_no_protocol_mismatch_on_orion(adapter: SocExplorerAdapter) -> None:
    verdict = adapter.call("validate_design", {"checks": ["protocol_mismatch"]})["result"]
    assert verdict["issue_count"] == 0


def test_bad_severity_argument(adapter: SocExplorerAdapter) -> None:
    assert adapter.call("validate_design", {"min_severity": "critical"})["error"]["code"] == "INVALID_ARGUMENT"
