from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import NotFoundError, ValidationError
from .models import Component, Design, Issue, Link
from .store import DesignStore


class MiniEda:
    """Small local EDA-like façade over a JSON design.

    This API is intentionally simple. Your MCP layer should sit on top of it —
    do not replace MiniEda wholesale. You may adapt or extend what tools expose
    (behavior, errors, payloads); you need not mirror these methods 1:1.
    """

    def __init__(self, design_path: str | Path) -> None:
        self._store = DesignStore(design_path)
        self._store.load()

    @property
    def design(self) -> Design:
        return self._store.design

    def reload(self) -> Design:
        return self._store.load()

    def list_components(self, kind: str | None = None) -> list[Component]:
        comps = list(self.design.components.values())
        if kind is not None:
            comps = [c for c in comps if c.kind == kind]
        return sorted(comps, key=lambda c: c.id)

    def get_component(self, component_id: str) -> Component:
        try:
            return self.design.components[component_id]
        except KeyError as exc:
            raise NotFoundError(f"Component not found: {component_id}") from exc

    def list_links(
        self, src: str | None = None, dst: str | None = None
    ) -> list[Link]:
        links = list(self.design.links.values())
        if src is not None:
            links = [link for link in links if link.src == src]
        if dst is not None:
            links = [link for link in links if link.dst == dst]
        return sorted(links, key=lambda link: link.id)

    def get_link(self, link_id: str) -> Link:
        try:
            return self.design.links[link_id]
        except KeyError as exc:
            raise NotFoundError(f"Link not found: {link_id}") from exc

    def search(self, query: str) -> list[dict[str, Any]]:
        """Case-sensitive substring search over ids, names, kinds, endpoints."""
        if not query:
            return []
        hits: list[dict[str, Any]] = []
        for comp in self.design.components.values():
            blob = f"{comp.id} {comp.name} {comp.kind}"
            if query in blob:
                hits.append({"type": "component", **comp.to_dict()})
        for link in self.design.links.values():
            blob = f"{link.id} {link.src} {link.dst}"
            if query in blob:
                hits.append({"type": "link", **link.to_dict()})
        return hits

    def update_property(
        self, element_id: str, prop_path: str, value: Any, *, persist: bool = True
    ) -> dict[str, Any]:
        """Update a property on a component or link.

        ``prop_path`` is a dotted path relative to the element's ``properties``
        dict, e.g. ``qos`` or ``bandwidth_mbps``.

        When ``persist`` is true (default), the design file is overwritten
        immediately via ``save()``.
        """
        if not prop_path or prop_path.startswith("/") or ".." in prop_path:
            raise ValidationError(f"Invalid property path: {prop_path!r}")

        element: Component | Link
        kind: str
        if element_id in self.design.components:
            element = self.design.components[element_id]
            kind = "component"
        elif element_id in self.design.links:
            element = self.design.links[element_id]
            kind = "link"
        else:
            raise NotFoundError(f"Element not found: {element_id}")

        _assign_path(element.properties, prop_path, value)
        if persist:
            self.save()
        return {"type": kind, **element.to_dict()}

    def validate(self) -> list[Issue]:
        """Run a *minimal* consistency check.

        This intentionally covers only a subset of possible issues.
        """
        issues: list[Issue] = []
        seen: set[str] = set()
        for comp_id in self.design.components:
            if comp_id in seen:
                issues.append(
                    Issue(
                        code="DUPLICATE_COMPONENT_ID",
                        message=f"Duplicate component id: {comp_id}",
                        element_id=comp_id,
                    )
                )
            seen.add(comp_id)

        for link in self.design.links.values():
            bw = link.properties.get("bandwidth_mbps")
            if bw is not None:
                try:
                    if float(bw) <= 0:
                        issues.append(
                            Issue(
                                code="NON_POSITIVE_BANDWIDTH",
                                message=f"bandwidth_mbps must be > 0 on {link.id}",
                                element_id=link.id,
                            )
                        )
                except (TypeError, ValueError):
                    issues.append(
                        Issue(
                            code="INVALID_BANDWIDTH",
                            message=f"bandwidth_mbps is not numeric on {link.id}",
                            element_id=link.id,
                        )
                    )
        return issues

    def export_report(self, fmt: str = "text") -> str | dict[str, Any]:
        design = self.design
        summary = {
            "name": design.name,
            "version": design.version,
            "component_count": len(design.components),
            "link_count": len(design.links),
            "components_by_kind": _count_by_kind(design),
            "issue_count": len(self.validate()),
        }
        if fmt == "json":
            return summary
        if fmt != "text":
            raise ValidationError(f"Unsupported report format: {fmt}")
        lines = [
            f"Design: {summary['name']} (v{summary['version']})",
            f"Components: {summary['component_count']}",
            f"Links: {summary['link_count']}",
            "By kind: "
            + ", ".join(
                f"{k}={v}" for k, v in sorted(summary["components_by_kind"].items())
            ),
            f"Validation issues (built-in checks): {summary['issue_count']}",
        ]
        return "\n".join(lines)

    def save(self) -> None:
        self._store.save()


def _count_by_kind(design: Design) -> dict[str, int]:
    out: dict[str, int] = {}
    for comp in design.components.values():
        out[comp.kind] = out.get(comp.kind, 0) + 1
    return out


def _assign_path(root: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur: dict[str, Any] = root
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value
