"""Tool implementations: one service class, one method per tool.

This is the **single source of truth** for behavior. The scenario adapter
(proof 1) and the MCP server (proof 2) both go through
``soc_explorer.registry``, which calls these methods — so what the scenarios
measure is exactly what an agent gets over MCP.

Design stance towards ``mini_eda``: it stays the owner of design state
(loading, property assignment, saving, its own validate). We add the layer it
lacks — resolution hints, ranked search, topology, richer checks, and a
mutation path that previews before it writes.
"""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mini_eda import MiniEda
from mini_eda.models import Component, Link

from . import schemas as S
from .errors import (
    InvalidArgumentError,
    NotFoundError,
    UnsafeMutationError,
    did_you_mean,
    from_eda_exception,
)
from .graph import DesignGraph, as_float, build_graph
from .report import render_markdown, render_text
from .search import search_design
from .validators import CHECK_NAMES, CheckContext, run_checks

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESIGN = ROOT / "data" / "designs" / "orion_soc.json"


class SocExplorer:
    """Stateful façade over one design file."""

    def __init__(self, design_path: str | Path | None = None) -> None:
        self.design_path = Path(design_path or DEFAULT_DESIGN)
        if not self.design_path.exists():
            raise InvalidArgumentError(
                f"Design file not found: {self.design_path}", path=str(self.design_path)
            )
        self.eda = MiniEda(self.design_path)
        self._graph = build_graph(self.eda.design)

    # -- internals -------------------------------------------------------

    @property
    def design(self):  # noqa: ANN201 - mini_eda.models.Design
        return self.eda.design

    @property
    def graph(self) -> DesignGraph:
        return self._graph

    def _rebuild_graph(self) -> None:
        """Only needed after topology changes; property edits keep it valid
        because the index holds references to the live Link objects."""
        self._graph = build_graph(self.design)

    def _check_context(self) -> CheckContext:
        return CheckContext(
            eda=self.eda,
            design=self.design,
            graph=self._graph,
            source_path=self.design_path,
        )

    def _require_component(self, component_id: str) -> Component:
        comp = self.design.components.get(component_id)
        if comp is not None:
            return comp
        if component_id in self.design.links:
            raise NotFoundError(
                f"{component_id!r} is a link id, not a component id",
                element_id=component_id,
                exists_as="link",
                use_tool="get_link",
            )
        raise NotFoundError(
            f"Component not found: {component_id!r}",
            element_id=component_id,
            did_you_mean=did_you_mean(component_id, self.design.components),
            component_count=len(self.design.components),
        )

    def _require_link(self, link_id: str) -> Link:
        link = self.design.links.get(link_id)
        if link is not None:
            return link
        if link_id in self.design.components:
            raise NotFoundError(
                f"{link_id!r} is a component id, not a link id",
                element_id=link_id,
                exists_as="component",
                use_tool="get_component",
            )
        raise NotFoundError(
            f"Link not found: {link_id!r}",
            element_id=link_id,
            did_you_mean=did_you_mean(link_id, self.design.links),
            link_count=len(self.design.links),
        )

    def _resolve_element(self, element_id: str) -> tuple[Component | Link, str]:
        if element_id in self.design.components:
            return self.design.components[element_id], "component"
        if element_id in self.design.links:
            return self.design.links[element_id], "link"
        candidates = list(self.design.components) + list(self.design.links)
        raise NotFoundError(
            f"Element not found: {element_id!r}",
            element_id=element_id,
            did_you_mean=did_you_mean(element_id, candidates),
        )

    def _component_row(self, comp: Component) -> dict[str, Any]:
        """Component payload enriched with how many links touch it.

        Cheap, and it makes an anomaly visible in a plain listing: on Orion,
        ``sram0`` shows ``link_count: 0``.
        """
        return {
            **comp.to_dict(),
            "link_count": self._graph.link_count(comp.id),
        }

    def design_sha256(self) -> str:
        return hashlib.sha256(self.design_path.read_bytes()).hexdigest()

    # -- read tools ------------------------------------------------------

    def describe_design(self, _: S.DescribeDesignInput) -> dict[str, Any]:
        """Orientation call: what this design is, and what can be asked about it."""
        design = self.design
        prop_keys: dict[str, dict[str, int]] = {"components": {}, "links": {}}
        for comp in design.components.values():
            for key in comp.properties:
                prop_keys["components"][key] = prop_keys["components"].get(key, 0) + 1
        for link in design.links.values():
            for key in link.properties:
                prop_keys["links"][key] = prop_keys["links"].get(key, 0) + 1

        kinds: dict[str, int] = {}
        clock_domains: set[str] = set()
        protocols: set[str] = set()
        for comp in design.components.values():
            kinds[comp.kind] = kinds.get(comp.kind, 0) + 1
            cd = self._graph.clock_domain(comp.id)
            if cd:
                clock_domains.add(cd)
            proto = comp.properties.get("protocol")
            if isinstance(proto, str):
                protocols.add(proto)
        for link in design.links.values():
            proto = link.properties.get("protocol")
            if isinstance(proto, str):
                protocols.add(proto)

        return {
            "name": design.name,
            "version": design.version,
            "description": design.description,
            "source_path": _display_path(self.design_path),
            "design_sha256": self.design_sha256(),
            "component_count": len(design.components),
            "link_count": len(design.links),
            "components_by_kind": dict(sorted(kinds.items())),
            "clock_domains": sorted(clock_domains),
            "protocols": sorted(protocols),
            "property_keys": {
                "components": dict(sorted(prop_keys["components"].items())),
                "links": dict(sorted(prop_keys["links"].items())),
            },
            "notes": list(design.notes),
            "checks_available": list(CHECK_NAMES),
        }

    def list_components(self, inp: S.ListComponentsInput) -> dict[str, Any]:
        """List components, optionally filtered by kind."""
        comps = self.eda.list_components(kind=inp.kind)
        rows = [self._component_row(c) for c in comps[: inp.limit]]
        kinds = sorted({c.kind for c in self.design.components.values()})
        result = {
            "count": len(rows),
            "total_matching": len(comps),
            "truncated": len(comps) > len(rows),
            "kind_filter": inp.kind,
            "kinds_available": kinds,
            "components": rows,
        }
        if inp.kind is not None and not comps:
            # An unknown kind is a legitimate query, not an error — but say so.
            result["note"] = (
                f"No component of kind {inp.kind!r}; known kinds: {', '.join(kinds)}"
            )
        return result

    def get_component(self, inp: S.GetComponentInput) -> dict[str, Any]:
        """Fetch one component with its immediate connectivity."""
        comp = self._require_component(inp.component_id)
        neighbors = self._graph.neighbors(comp.id)
        return {
            **self._component_row(comp),
            "type": "component",
            "clock_domain": self._graph.clock_domain(comp.id),
            "outgoing_links": [edge["link_id"] for edge in neighbors["outgoing"]],
            "incoming_links": [edge["link_id"] for edge in neighbors["incoming"]],
            "bandwidth_balance": self._graph.bandwidth_balance(comp.id),
        }

    def list_links(self, inp: S.ListLinksInput) -> dict[str, Any]:
        """List links, optionally filtered by src and/or dst component id."""
        links = self.eda.list_links(src=inp.src, dst=inp.dst)
        rows = []
        for link in links[: inp.limit]:
            rows.append(
                {
                    **link.to_dict(),
                    "src_exists": self._graph.exists(link.src),
                    "dst_exists": self._graph.exists(link.dst),
                }
            )
        return {
            "count": len(rows),
            "total_matching": len(links),
            "truncated": len(links) > len(rows),
            "filters": {"src": inp.src, "dst": inp.dst},
            "links": rows,
        }

    def get_link(self, inp: S.GetLinkInput) -> dict[str, Any]:
        """Fetch one link, flagging endpoints that do not resolve."""
        link = self._require_link(inp.link_id)
        payload = {
            **link.to_dict(),
            "type": "link",
            "src_exists": self._graph.exists(link.src),
            "dst_exists": self._graph.exists(link.dst),
            "src_clock_domain": self._graph.clock_domain(link.src),
            "dst_clock_domain": self._graph.clock_domain(link.dst),
        }
        payload["crosses_clock_domain"] = (
            payload["src_clock_domain"] is not None
            and payload["dst_clock_domain"] is not None
            and payload["src_clock_domain"] != payload["dst_clock_domain"]
        )
        return payload

    def search(self, inp: S.SearchInput) -> dict[str, Any]:
        """Ranked search over ids, names, kinds, endpoints and properties.

        Every hit says **which field matched and how**, so an agent can tell an
        exact id from an incidental substring. On Orion, ``search("r0")``
        returns the router ``r0`` (exact id, score 1.0) ahead of ``ddr0``
        (substring, 0.6) and of the links that merely reference ``r0``.
        """
        return search_design(self.design, inp, self._component_row)

    def get_neighbors(self, inp: S.GetNeighborsInput) -> dict[str, Any]:
        """Direct peers of a component, including edges whose peer is missing."""
        comp = self._require_component(inp.component_id)
        neighbors = self._graph.neighbors(comp.id, inp.direction)
        return {
            "component": {"id": comp.id, "kind": comp.kind, "name": comp.name},
            "direction": inp.direction,
            "outgoing": neighbors["outgoing"],
            "incoming": neighbors["incoming"],
            "link_count": self._graph.link_count(comp.id),
        }

    def find_path(self, inp: S.FindPathInput) -> dict[str, Any]:
        """Shortest directed path between two components, with its bottleneck.

        Link direction is honoured, so a missing path is information, not a
        failure: it is reported as ``found: false`` with a reason, never as an
        error.
        """
        self._require_component(inp.src)
        self._require_component(inp.dst)
        path = self._graph.find_path(inp.src, inp.dst, inp.max_hops)
        if not path["found"]:
            return path

        links = [self.design.links[link_id] for link_id in path["links"]]
        latencies = [as_float(link.properties.get("latency_ns")) for link in links]
        bandwidths = [as_float(link.properties.get("bandwidth_mbps")) for link in links]
        known_bw = [(link.id, bw) for link, bw in zip(links, bandwidths) if bw is not None]
        bottleneck = min(known_bw, key=lambda item: item[1]) if known_bw else None
        domains = [self._graph.clock_domain(cid) for cid in path["components"]]
        return {
            "found": True,
            "hops": path["hops"],
            "components": [
                {"id": cid, "kind": self.design.components[cid].kind, "clock_domain": cd}
                for cid, cd in zip(path["components"], domains)
            ],
            "links": [link.to_dict() for link in links],
            "total_latency_ns": sum(v for v in latencies if v is not None) or None,
            "links_without_latency": [
                link.id for link, v in zip(links, latencies) if v is None
            ],
            "bottleneck": {"link_id": bottleneck[0], "bandwidth_mbps": bottleneck[1]}
            if bottleneck
            else None,
            "clock_domain_crossings": sum(
                1 for a, b in zip(domains, domains[1:]) if a and b and a != b
            ),
        }

    def validate_design(self, inp: S.ValidateDesignInput) -> dict[str, Any]:
        """Run the consistency checks and return a structured verdict."""
        return run_checks(self._check_context(), checks=inp.checks, min_severity=inp.min_severity)

    def export_report(self, inp: S.ExportReportInput) -> str | dict[str, Any]:
        """Short design report: inventory, health, hotspots.

        The built-in and extended issue counts are shown side by side on
        purpose — on Orion that is ``0`` versus ``11``, which is the single
        most useful thing a reviewer can read about this design.
        """
        summary = self.eda.export_report("json")  # keep mini_eda in the loop
        assert isinstance(summary, dict)
        verdict = run_checks(self._check_context())
        top = [i for i in verdict["issues"] if i["severity"] in ("error", "warning")]
        hotspots = [
            self._graph.bandwidth_balance(cid)
            for cid in sorted(self.design.components)
            if self._graph.bandwidth_balance(cid)["oversubscription_ratio"] is not None
            and self._graph.bandwidth_balance(cid)["oversubscription_ratio"] > 1
        ]
        payload = {
            "design": summary["name"],
            "version": summary["version"],
            "source_path": _display_path(self.design_path),
            "design_sha256": self.design_sha256(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "component_count": summary["component_count"],
            "link_count": summary["link_count"],
            "components_by_kind": summary["components_by_kind"],
            "builtin_issue_count": summary["issue_count"],
            "extended_issue_count": verdict["issue_count"],
            "issues_by_severity": verdict["by_severity"],
            "issues_by_code": verdict["by_code"],
            "top_issues": top,
            "oversubscribed_components": hotspots,
        }
        if inp.format == "json":
            return payload
        if inp.format == "markdown":
            return render_markdown(payload)
        return render_text(payload)

    # -- write tools -----------------------------------------------------

    def update_property(self, inp: S.UpdatePropertyInput) -> dict[str, Any]:
        """Update one property on a component or link, previewing by default.

        The value is assigned through ``MiniEda.update_property(persist=False)``
        so dotted-path semantics and path rejection stay mini_eda's job.

        Note the scope: ``prop_path`` is relative to the element's
        ``properties`` object, so structural fields cannot be reached from
        here. ``prop_path="dst"`` creates ``properties.dst`` and does *not*
        retarget a link — use ``set_link_endpoint`` for that.
        """
        element, element_type = self._resolve_element(inp.element_id)
        before_props = copy.deepcopy(element.properties)
        old_value, existed = _read_path(before_props, inp.prop_path)

        def apply() -> None:
            self.eda.update_property(inp.element_id, inp.prop_path, inp.value, persist=False)

        def undo() -> None:
            element.properties.clear()
            element.properties.update(copy.deepcopy(before_props))

        change = {
            "field": f"properties.{inp.prop_path}",
            "prop_path": inp.prop_path,
            "operation": "created"
            if not existed
            else ("unchanged" if old_value == inp.value else "updated"),
            "old_value": old_value,
            "new_value": inp.value,
            "old_type": type(old_value).__name__ if existed else None,
            "new_type": type(inp.value).__name__,
            "type_changed": existed and type(old_value) is not type(inp.value),
        }
        return self._guarded_mutation(
            element_id=inp.element_id,
            element_type=element_type,
            change=change,
            apply=apply,
            undo=undo,
            element=element,
            persist=inp.persist,
            force=inp.force,
        )

    def set_link_endpoint(self, inp: S.SetLinkEndpointInput) -> dict[str, Any]:
        """Retarget a link's ``src`` or ``dst`` to an existing component.

        This is the one structural edit we expose, because it is the only way
        to repair the class of defect the checks actually find on Orion (a
        dangling endpoint). It refuses to point a link at a component that
        does not exist — creating the very bug we detect — and it goes through
        the same preview / validation-diff / backup policy as
        ``update_property``.
        """
        link = self._require_link(inp.link_id)
        self._require_component(inp.component_id)  # refuse to create a dangling endpoint
        old_value = getattr(link, inp.role)

        def apply() -> None:
            setattr(link, inp.role, inp.component_id)

        def undo() -> None:
            setattr(link, inp.role, old_value)

        change = {
            "field": inp.role,
            "operation": "unchanged" if old_value == inp.component_id else "updated",
            "old_value": old_value,
            "new_value": inp.component_id,
            "old_type": type(old_value).__name__,
            "new_type": type(inp.component_id).__name__,
            "type_changed": False,
        }
        return self._guarded_mutation(
            element_id=inp.link_id,
            element_type="link",
            change=change,
            apply=apply,
            undo=undo,
            element=link,
            persist=inp.persist,
            force=inp.force,
        )

    # -- mutation safety policy -------------------------------------------

    def _guarded_mutation(
        self,
        *,
        element_id: str,
        element_type: str,
        change: dict[str, Any],
        apply: Callable[[], None],
        undo: Callable[[], None],
        element: Component | Link,
        persist: bool,
        force: bool,
    ) -> dict[str, Any]:
        """Shared write policy for every mutating tool.

        1. snapshot the validation verdict;
        2. apply the change **in memory only** and rebuild the derived graph;
        3. re-validate and diff, so the caller sees what the edit created or
           resolved;
        4. refuse a write that introduces a new *error*-severity issue unless
           ``force=True`` (``UNSAFE_MUTATION``);
        5. persist only when asked, after copying the file to
           ``<design>.bak.json``; otherwise roll back.

        A preview never touches the file, and any failure rolls back — the
        in-memory design is left exactly as it was found.
        """
        before = run_checks(self._check_context())
        try:
            apply()
            self._rebuild_graph()
        except Exception as exc:  # mini_eda validates paths and may reject
            undo()
            self._rebuild_graph()
            raise from_eda_exception(exc) from exc

        try:
            after = run_checks(self._check_context())
            new_issues = _issue_diff(after["issues"], before["issues"])
            resolved_issues = _issue_diff(before["issues"], after["issues"])
            blocking = [issue for issue in new_issues if issue["severity"] == "error"]

            if blocking and not force:
                raise UnsafeMutationError(
                    f"Refusing to change {change['field']!r} on {element_id!r}: "
                    f"it introduces {len(blocking)} error-severity issue(s)",
                    element_id=element_id,
                    field=change["field"],
                    blocking_issues=blocking,
                    retry_with={"force": True},
                )

            # Captured while the change is applied, so a preview shows the
            # element as it *would* be, without ever persisting it.
            element_payload = element.to_dict()

            backup_path: str | None = None
            if persist:
                backup_path = self._backup()
                self.eda.save()
                self._rebuild_graph()
            else:
                undo()
                self._rebuild_graph()

            return {
                "element_id": element_id,
                "element_type": element_type,
                "change": change,
                "persisted": persist,
                "dry_run": not persist,
                "forced": bool(blocking and force),
                "backup_path": backup_path,
                "element": element_payload,
                "validation": {
                    "before": before["by_severity"],
                    "after": after["by_severity"],
                    "new_issues": new_issues,
                    "resolved_issues": resolved_issues,
                },
            }
        except UnsafeMutationError:
            undo()
            self._rebuild_graph()
            raise

    def _backup(self) -> str:
        """Copy the design next to itself before overwriting it.

        ``DesignStore.save()`` documents that it overwrites in place with no
        backup; the name matches the pattern .gitignore already excludes.
        """
        backup = self.design_path.with_suffix(".bak.json")
        backup.write_text(self.design_path.read_text(encoding="utf-8"), encoding="utf-8")
        return _display_path(backup)


# --- helpers -----------------------------------------------------------


def _display_path(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise (tests run on copies)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _read_path(root: dict[str, Any], path: str) -> tuple[Any, bool]:
    cur: Any = root
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None, False
        cur = cur[part]
    return cur, True


def _issue_diff(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Issues present in ``left`` and absent from ``right``."""
    def key(issue: dict[str, Any]) -> tuple[str, str | None, str]:
        return (issue["code"], issue["element_id"], issue["message"])

    seen = {key(i) for i in right}
    return [i for i in left if key(i) not in seen]
