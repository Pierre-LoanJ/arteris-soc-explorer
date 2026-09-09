"""Read tools: shapes, ranking, topology, and the quality of failures."""

from __future__ import annotations

from soc_explorer.adapter import SocExplorerAdapter


def result(adapter: SocExplorerAdapter, tool: str, args: dict | None = None):
    response = adapter.call(tool, args or {})
    assert response["ok"] is True, response
    return response["result"]


def test_describe_design_orients_the_agent(adapter: SocExplorerAdapter) -> None:
    described = result(adapter, "describe_design")
    assert described["name"] == "orion_soc"
    assert described["component_count"] == 9
    assert described["link_count"] == 9
    assert described["components_by_kind"] == {
        "initiator": 3,
        "observer": 1,
        "router": 2,
        "target": 3,
    }
    # The check names it advertises must be the ones validate_design accepts.
    assert "dangling_link_endpoint" in described["checks_available"]
    assert result(adapter, "validate_design", {"checks": described["checks_available"]})


def test_list_components_exposes_isolation(adapter: SocExplorerAdapter) -> None:
    listed = result(adapter, "list_components")
    assert listed["count"] == 9
    by_id = {component["id"]: component for component in listed["components"]}
    assert by_id["sram0"]["link_count"] == 0  # Orion's orphan memory
    assert by_id["r0"]["link_count"] == 7  # 7 distinct links, self-loop counted once


def test_unknown_kind_is_an_empty_answer_not_an_error(adapter: SocExplorerAdapter) -> None:
    listed = result(adapter, "list_components", {"kind": "quantum"})
    assert listed["count"] == 0
    assert "quantum" in listed["note"] and "router" in listed["note"]


def test_get_component_carries_connectivity(adapter: SocExplorerAdapter) -> None:
    cpu = result(adapter, "get_component", {"component_id": "cpu0"})
    assert cpu["kind"] == "initiator"
    assert cpu["clock_domain"] == "cd_cpu"
    assert cpu["outgoing_links"] == ["L1"]
    assert cpu["bandwidth_balance"]["egress_mbps"] == 12800


def test_not_found_suggests_the_right_id(adapter: SocExplorerAdapter) -> None:
    error = adapter.call("get_component", {"component_id": "sram_l2"})["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["details"]["did_you_mean"] == ["sram0"]


def test_asking_for_a_link_as_a_component_says_so(adapter: SocExplorerAdapter) -> None:
    error = adapter.call("get_component", {"component_id": "L1"})["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["details"]["exists_as"] == "link"
    assert error["details"]["use_tool"] == "get_link"


def test_get_link_flags_the_broken_endpoint(adapter: SocExplorerAdapter) -> None:
    link = result(adapter, "get_link", {"link_id": "L7"})
    assert link["dst"] == "sram_l2"
    assert link["src_exists"] is True
    assert link["dst_exists"] is False


def test_search_ranks_the_exact_id_first(adapter: SocExplorerAdapter) -> None:
    hits = result(adapter, "search", {"query": "r0"})["hits"]
    assert hits[0]["id"] == "r0"
    assert hits[0]["score"] == 1.0
    assert hits[0]["matched_fields"][0]["match"] == "exact"
    # ddr0 is a legitimate substring hit, but it must rank below the exact one.
    ddr0 = next(hit for hit in hits if hit["id"] == "ddr0")
    assert ddr0["score"] < hits[0]["score"]
    assert ddr0["matched_fields"][0]["match"] == "substring"


def test_search_is_case_insensitive_by_default(adapter: SocExplorerAdapter) -> None:
    ids = [hit["id"] for hit in result(adapter, "search", {"query": "SRAM"})["hits"]]
    assert "sram0" in ids  # matched on the id, which is lowercase
    assert "L7" in ids  # matched on the endpoint that references it


def test_search_can_be_made_case_sensitive(adapter: SocExplorerAdapter) -> None:
    hits = result(adapter, "search", {"query": "SRAM", "case_sensitive": True})["hits"]
    assert [hit["id"] for hit in hits] == ["sram0"]  # only the display name matches
    assert hits[0]["matched_fields"][0]["field"] == "name"


def test_search_reaches_properties(adapter: SocExplorerAdapter) -> None:
    hits = result(adapter, "search", {"query": "cd_noc"})["hits"]
    assert {hit["id"] for hit in hits} == {"r0", "r1"}
    assert not result(adapter, "search", {"query": "cd_noc", "search_properties": False})["hits"]


def test_empty_query_is_rejected(adapter: SocExplorerAdapter) -> None:
    assert adapter.call("search", {"query": ""})["error"]["code"] == "INVALID_ARGUMENT"


def test_neighbors_follow_direction(adapter: SocExplorerAdapter) -> None:
    out = result(adapter, "get_neighbors", {"component_id": "r0", "direction": "out"})
    assert out["incoming"] == []
    assert {edge["peer_id"] for edge in out["outgoing"]} == {"r0", "r1", "ddr0"}
    both = result(adapter, "get_neighbors", {"component_id": "r0"})
    assert both["link_count"] == 7


def test_path_reports_bottleneck_and_crossings(adapter: SocExplorerAdapter) -> None:
    path = result(adapter, "find_path", {"src": "cpu0", "dst": "ddr0"})
    assert path["found"] is True
    assert [link["id"] for link in path["links"]] == ["L1", "L5"]
    assert path["total_latency_ns"] == 22
    assert path["bottleneck"] == {"link_id": "L1", "bandwidth_mbps": 12800.0}
    assert path["clock_domain_crossings"] == 2


def test_unreachable_target_is_an_answer_not_a_failure(adapter: SocExplorerAdapter) -> None:
    path = result(adapter, "find_path", {"src": "cpu0", "dst": "sram0"})
    assert path["found"] is False
    assert "No directed path" in path["reason"]


def test_path_to_unknown_component_is_an_error(adapter: SocExplorerAdapter) -> None:
    error = adapter.call("find_path", {"src": "cpu0", "dst": "sram_l2"})["error"]
    assert error["code"] == "NOT_FOUND"


def test_self_loop_does_not_hang_the_search(adapter: SocExplorerAdapter) -> None:
    assert result(adapter, "find_path", {"src": "r0", "dst": "periph0"})["hops"] == 2


def test_report_text_mentions_the_design_and_both_issue_counts(adapter: SocExplorerAdapter) -> None:
    text = result(adapter, "export_report", {"format": "text"})
    assert "orion_soc" in text
    assert "11 extended" in text and "0 from mini_eda" in text


def test_report_json_and_markdown(adapter: SocExplorerAdapter) -> None:
    payload = result(adapter, "export_report", {"format": "json"})
    assert payload["extended_issue_count"] == 11
    assert payload["builtin_issue_count"] == 0
    assert len(payload["oversubscribed_components"]) == 2
    assert "| Severity |" in result(adapter, "export_report", {"format": "markdown"})


def test_unsupported_report_format(adapter: SocExplorerAdapter) -> None:
    assert adapter.call("export_report", {"format": "pdf"})["error"]["code"] == "INVALID_ARGUMENT"
