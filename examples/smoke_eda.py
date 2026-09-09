"""Smoke script: explore the mini-EDA without MCP."""

from __future__ import annotations

from pathlib import Path

from mini_eda import MiniEda

DESIGN = Path(__file__).resolve().parents[1] / "data" / "designs" / "orion_soc.json"


def main() -> None:
    eda = MiniEda(DESIGN)
    print(eda.export_report("text"))
    print("--- components ---")
    for comp in eda.list_components():
        print(f"  {comp.id:12} {comp.kind:10} {comp.name}")
    print("--- sample search: 'r0' ---")
    for hit in eda.search("r0"):
        print(f"  {hit.get('type')} {hit.get('id')}")
    print("--- validate (built-in) ---")
    issues = eda.validate()
    if not issues:
        print("  (no issues reported by built-in checks)")
    for issue in issues:
        print(f"  [{issue.severity}] {issue.code}: {issue.message}")


if __name__ == "__main__":
    main()
