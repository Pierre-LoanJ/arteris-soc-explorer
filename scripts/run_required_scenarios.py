#!/usr/bin/env python3
"""Run required scenarios against the candidate adapter and write artifacts.

Usage:
  python scripts/run_required_scenarios.py
  python scripts/run_required_scenarios.py --adapter soc_explorer.adapter:get_adapter
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data" / "designs" / "orion_soc.json"
ARTIFACTS = ROOT / "artifacts"


def _load_adapter(spec: str) -> Any:
    module_name, _, attr = spec.partition(":")
    if not attr:
        attr = "get_adapter"
    mod = importlib.import_module(module_name)
    factory: Callable[[], Any] = getattr(mod, attr)
    return factory()


def _design_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(adapter: Any) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []

    def record(scenario_id: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        response = adapter.call(tool, args)
        entry = {
            "id": scenario_id,
            "tool": tool,
            "arguments": args,
            "response": response,
        }
        scenarios.append(entry)
        return response

    # S1 — inventory
    record("S1_list_components", "list_components", {})

    # S2 — known component
    record("S2_get_cpu0", "get_component", {"component_id": "cpu0"})

    # S3 — structured not-found
    record("S3_get_missing", "get_component", {"component_id": "no_such_block"})

    # S4 — validation as implemented by candidate
    record("S4_validate", "validate_design", {})

    # S5 — search behavior (observability / false positives)
    record("S5_search_r0", "search", {"query": "r0"})

    # S6 — mutation + read-back (use persist false if adapter supports it;
    # template persists — runner uses a note field only)
    record(
        "S6_update_qos",
        "update_property",
        {
            "element_id": "cpu0",
            "prop_path": "qos",
            "value": "medium",
            "persist": False,
        },
    )
    record("S6b_reread_cpu0", "get_component", {"component_id": "cpu0"})

    # S7 — report
    record("S7_report", "export_report", {"format": "text"})

    tools = adapter.list_tools()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design_path": str(DESIGN.relative_to(ROOT)),
        "design_sha256": _design_fingerprint(DESIGN),
        "tools": tools,
        "scenarios": scenarios,
    }


def _write_manifest(tools: list[dict[str, Any]]) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "design_sha256": _design_fingerprint(DESIGN),
        "tools": tools,
    }
    (ARTIFACTS / "tools_manifest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adapter",
        default="soc_explorer.adapter:get_adapter",
        help="module:factory for the candidate adapter",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    adapter = _load_adapter(args.adapter)
    payload = _run(adapter)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / "scenario_results.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_manifest(payload["tools"])

    notes = ARTIFACTS / "NOTES.md"
    if not notes.exists():
        notes.write_text(
            "\n".join(
                [
                    "# Submission notes",
                    "",
                    "- Time spent (hours):",
                    "- AI assistants used:",
                    "- What I designed myself vs AI-assisted:",
                    "- Surprises observed while running Orion (facts, not guesses):",
                    "- Known limits of my solution:",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    print(f"Wrote {out.relative_to(ROOT)}")
    print(f"Wrote {Path('artifacts/tools_manifest.json')}")
    print(f"Scenarios: {len(payload['scenarios'])}, tools: {len(payload['tools'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
