"""Rendering of the design report.

Kept apart from the report's *content* (assembled in ``tools.export_report``)
so a format change never risks touching the numbers.
"""

from __future__ import annotations

from typing import Any


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Design: {payload['design']} (v{payload['version']})",
        f"Source: {payload['source_path']} sha256={payload['design_sha256'][:12]}",
        f"Components: {payload['component_count']} | Links: {payload['link_count']}",
        "By kind: "
        + ", ".join(f"{k}={v}" for k, v in sorted(payload["components_by_kind"].items())),
        f"Issues: {payload['extended_issue_count']} extended "
        f"({payload['issues_by_severity']['error']} error, "
        f"{payload['issues_by_severity']['warning']} warning, "
        f"{payload['issues_by_severity']['info']} info) "
        f"vs {payload['builtin_issue_count']} from mini_eda built-in checks",
    ]
    if payload["top_issues"]:
        lines.append("Actionable issues:")
        lines += [
            f"  [{i['severity']}] {i['code']} {i['element_id']}: {i['message']}"
            for i in payload["top_issues"]
        ]
    if payload["oversubscribed_components"]:
        lines.append("Oversubscribed components:")
        lines += [
            f"  {h['component_id']}: {h['ingress_mbps']:.0f} in / "
            f"{h['egress_mbps']:.0f} out Mbps (ratio {h['oversubscription_ratio']})"
            for h in payload["oversubscribed_components"]
        ]
    return "\n".join(lines)


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['design']} — design report",
        "",
        f"- **Version**: {payload['version']}",
        f"- **Source**: `{payload['source_path']}` (`sha256:{payload['design_sha256'][:12]}`)",
        f"- **Components / links**: {payload['component_count']} / {payload['link_count']}",
        f"- **Issues**: {payload['extended_issue_count']} extended "
        f"vs {payload['builtin_issue_count']} built-in",
        "",
        "## Issues",
        "",
        "| Severity | Code | Element | Message |",
        "| --- | --- | --- | --- |",
    ]
    for issue in payload["top_issues"]:
        lines.append(
            f"| {issue['severity']} | `{issue['code']}` | `{issue['element_id']}` | {issue['message']} |"
        )
    if not payload["top_issues"]:
        lines.append("| — | — | — | no error/warning issue |")
    return "\n".join(lines)
