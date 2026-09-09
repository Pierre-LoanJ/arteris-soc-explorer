"""Consistency checks over a design.

``MiniEda.validate()`` intentionally covers "only a subset of possible
issues" — and on Orion it reports **zero** issues while the fixture contains a
dangling link, an unreachable memory, a self-loop and a component without a
clock domain. Worse, its ``DUPLICATE_COMPONENT_ID`` check iterates over the
keys of a ``dict``, so it can never fire; duplicates can only be caught on the
raw JSON, before ``DesignStore.load()`` silently collapses them.

So this module *extends* rather than replaces: check ``builtin_bandwidth``
delegates to ``MiniEda.validate()`` (keeping it the source of truth for what
it does cover), and the other checks add the topology/coherence layer.

Each check is an independent, named function so an agent can request a subset
(``validate_design(checks=["dangling_link_endpoint"])``) and so every issue
carries the name of the rule that produced it.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from mini_eda import MiniEda
from mini_eda.models import Design

from .errors import InvalidArgumentError, did_you_mean
from .graph import DesignGraph

SEVERITIES = ("error", "warning", "info")


@dataclass
class CheckContext:
    """Everything a check may read. Nothing here is mutated."""

    eda: MiniEda
    design: Design
    graph: DesignGraph
    source_path: Path | None = None


Check = Callable[[CheckContext], Iterator[dict[str, Any]]]


def _issue(
    check: str,
    code: str,
    message: str,
    severity: str = "warning",
    element_id: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    """Issue payload: a superset of ``mini_eda.models.Issue.to_dict()``."""
    payload = {
        "code": code,
        "message": message,
        "element_id": element_id,
        "severity": severity,
        "check": check,
    }
    if details:
        payload["details"] = details
    return payload


# --- checks ------------------------------------------------------------


def builtin_bandwidth(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """Delegate to ``MiniEda.validate()`` so we never contradict the core API."""
    for issue in ctx.eda.validate():
        yield _issue(
            "builtin_bandwidth",
            issue.code,
            issue.message,
            issue.severity,
            issue.element_id,
            delegated_to="mini_eda.MiniEda.validate",
        )


def dangling_link_endpoint(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """A link references a component id that does not exist."""
    for broken in ctx.graph.broken_endpoints:
        yield _issue(
            "dangling_link_endpoint",
            "DANGLING_LINK_ENDPOINT",
            f"Link {broken.link_id} has {broken.role}={broken.missing_id!r}, "
            "which is not a component id",
            "error",
            broken.link_id,
            role=broken.role,
            missing_id=broken.missing_id,
            did_you_mean=did_you_mean(broken.missing_id, ctx.design.components),
        )


def unconnected_component(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """A component no link touches — dead silicon, or a typo elsewhere."""
    for comp_id in ctx.graph.unconnected_components():
        comp = ctx.design.components[comp_id]
        yield _issue(
            "unconnected_component",
            "UNCONNECTED_COMPONENT",
            f"Component {comp_id} ({comp.name}) has no incoming or outgoing link",
            "error" if comp.kind in ("initiator", "target") else "warning",
            comp_id,
            kind=comp.kind,
            name=comp.name,
        )


def self_loop(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """A link whose src and dst are the same component."""
    for link in sorted(ctx.design.links.values(), key=lambda l: l.id):
        if link.src == link.dst:
            yield _issue(
                "self_loop",
                "SELF_LOOP",
                f"Link {link.id} connects {link.src} to itself",
                "warning",
                link.id,
                component_id=link.src,
            )


def missing_clock_domain(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """Component without ``clock_domain``: timing analysis cannot be done."""
    for comp_id in sorted(ctx.design.components):
        if ctx.graph.clock_domain(comp_id) is None:
            comp = ctx.design.components[comp_id]
            yield _issue(
                "missing_clock_domain",
                "MISSING_CLOCK_DOMAIN",
                f"Component {comp_id} ({comp.name}) has no clock_domain property",
                "warning",
                comp_id,
                kind=comp.kind,
            )


def clock_domain_crossing(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """Link between two different clock domains.

    Not a defect in itself — it is a *design implication* (synchronisation
    needed), hence severity ``info``. Emitted so an agent can enumerate CDC
    paths, which is a real question asked of interconnect tooling.
    """
    for link in sorted(ctx.design.links.values(), key=lambda l: l.id):
        src_cd = ctx.graph.clock_domain(link.src)
        dst_cd = ctx.graph.clock_domain(link.dst)
        if src_cd is None or dst_cd is None or src_cd == dst_cd:
            continue
        yield _issue(
            "clock_domain_crossing",
            "CLOCK_DOMAIN_CROSSING",
            f"Link {link.id} crosses {src_cd} -> {dst_cd}",
            "info",
            link.id,
            src=link.src,
            dst=link.dst,
            src_clock_domain=src_cd,
            dst_clock_domain=dst_cd,
        )


def protocol_mismatch(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """Link protocol contradicting an endpoint's own protocol.

    Only compared when both sides declare one; routers in Orion declare none,
    so this check reports nothing on the current fixture (verified, not
    assumed) and exists as a guard for edited designs.
    """
    for link in sorted(ctx.design.links.values(), key=lambda l: l.id):
        link_proto = link.properties.get("protocol")
        if not isinstance(link_proto, str):
            continue
        for role, ref in (("src", link.src), ("dst", link.dst)):
            comp = ctx.design.components.get(ref)
            if comp is None:
                continue
            comp_proto = comp.properties.get("protocol")
            if isinstance(comp_proto, str) and comp_proto != link_proto:
                yield _issue(
                    "protocol_mismatch",
                    "PROTOCOL_MISMATCH",
                    f"Link {link.id} declares protocol {link_proto!r} but its "
                    f"{role} {ref} declares {comp_proto!r}",
                    "warning",
                    link.id,
                    role=role,
                    component_id=ref,
                    link_protocol=link_proto,
                    component_protocol=comp_proto,
                )


def bandwidth_oversubscription(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """Inbound bandwidth exceeding outbound bandwidth on a node.

    A structural smell rather than a proof of failure (traffic is not
    necessarily concurrent), so severity is ``warning`` and the payload lists
    the links used, making the number auditable by a human.
    """
    for comp_id in sorted(ctx.design.components):
        balance = ctx.graph.bandwidth_balance(comp_id)
        ingress, egress = balance["ingress_mbps"], balance["egress_mbps"]
        if not ingress or not egress or ingress <= egress:
            continue
        yield _issue(
            "bandwidth_oversubscription",
            "BANDWIDTH_OVERSUBSCRIPTION",
            f"Component {comp_id} receives {ingress:.0f} Mbps but can only "
            f"forward {egress:.0f} Mbps (ratio {balance['oversubscription_ratio']})",
            "warning",
            comp_id,
            ingress_mbps=ingress,
            egress_mbps=egress,
            ratio=balance["oversubscription_ratio"],
            ingress_links=[link.id for link in ctx.graph.in_links(comp_id)],
            egress_links=[link.id for link in ctx.graph.out_links(comp_id)],
        )


def duplicate_id_in_source(ctx: CheckContext) -> Iterator[dict[str, Any]]:
    """Duplicate ids in the *file*, which loading would silently collapse.

    This is the check ``MiniEda.validate()`` believes it performs. It has to
    read the raw JSON: by the time the design is a ``dict``, the evidence is
    already gone.
    """
    if ctx.source_path is None or not ctx.source_path.exists():
        return
    raw = json.loads(ctx.source_path.read_text(encoding="utf-8"))
    for section, label in (("components", "COMPONENT"), ("links", "LINK")):
        counts = Counter(item.get("id") for item in raw.get(section, []))
        for element_id, count in sorted(counts.items()):
            if count > 1:
                yield _issue(
                    "duplicate_id_in_source",
                    f"DUPLICATE_{label}_ID",
                    f"{label.title()} id {element_id!r} appears {count} times in "
                    "the source file; only the last one survives loading",
                    "error",
                    element_id,
                    occurrences=count,
                )


CHECKS: dict[str, Check] = {
    "builtin_bandwidth": builtin_bandwidth,
    "duplicate_id_in_source": duplicate_id_in_source,
    "dangling_link_endpoint": dangling_link_endpoint,
    "unconnected_component": unconnected_component,
    "self_loop": self_loop,
    "missing_clock_domain": missing_clock_domain,
    "clock_domain_crossing": clock_domain_crossing,
    "protocol_mismatch": protocol_mismatch,
    "bandwidth_oversubscription": bandwidth_oversubscription,
}

CHECK_NAMES = tuple(CHECKS)


def run_checks(
    ctx: CheckContext,
    checks: list[str] | None = None,
    min_severity: str = "info",
) -> dict[str, Any]:
    """Run the selected checks and return a structured, sorted verdict."""
    if min_severity not in SEVERITIES:
        raise InvalidArgumentError(
            f"Unknown severity: {min_severity!r}",
            allowed=list(SEVERITIES),
        )
    names = list(checks) if checks else list(CHECK_NAMES)
    unknown = [name for name in names if name not in CHECKS]
    if unknown:
        raise InvalidArgumentError(
            f"Unknown check(s): {', '.join(sorted(unknown))}",
            unknown_checks=sorted(unknown),
            available_checks=list(CHECK_NAMES),
        )

    threshold = SEVERITIES.index(min_severity)
    issues = [
        issue
        for name in names
        for issue in CHECKS[name](ctx)
        if SEVERITIES.index(issue["severity"]) <= threshold
    ]
    issues.sort(key=lambda i: (SEVERITIES.index(i["severity"]), i["code"], i["element_id"] or ""))

    by_severity = {sev: 0 for sev in SEVERITIES}
    for issue in issues:
        by_severity[issue["severity"]] += 1
    return {
        "design": ctx.design.name,
        "checks_run": names,
        "min_severity": min_severity,
        "issue_count": len(issues),
        "by_severity": by_severity,
        "by_code": dict(sorted(Counter(i["code"] for i in issues).items())),
        "issues": issues,
    }
