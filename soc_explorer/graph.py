"""Derived read-only view of a design: adjacency, paths, bandwidth balance.

``mini_eda`` stores components and links as two flat dicts and offers no
topology query at all. Every interesting question an agent asks ("what is
connected to r0?", "can cpu0 reach ddr0?", "is this router oversubscribed?")
needs an index, so we build one *derived* structure and never mutate design
state from here.

Two deliberate choices:

- links are indexed even when an endpoint does not exist, so a broken link is
  observable instead of silently dropped (Orion's ``L7`` -> ``sram_l2``);
- traversal is **directed** (src -> dst), which is the semantics of a link.
  As a result ``find_path("cpu0", "sram0")`` finds nothing on Orion, and that
  is the correct answer: the only link into the SRAM is the broken one.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from mini_eda.models import Design, Link

Direction = Literal["out", "in", "both"]


def as_float(value: Any) -> float | None:
    """Coerce a property to float, or None when it is absent/not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class BrokenEndpoint:
    link_id: str
    role: Literal["src", "dst"]
    missing_id: str


@dataclass
class DesignGraph:
    """Adjacency index over a loaded design. Rebuild it after any mutation."""

    design: Design
    outgoing: dict[str, list[Link]] = field(default_factory=dict)
    incoming: dict[str, list[Link]] = field(default_factory=dict)
    broken_endpoints: list[BrokenEndpoint] = field(default_factory=list)

    def __post_init__(self) -> None:
        known = set(self.design.components)
        for link in sorted(self.design.links.values(), key=lambda l: l.id):
            self.outgoing.setdefault(link.src, []).append(link)
            self.incoming.setdefault(link.dst, []).append(link)
            for role, ref in (("src", link.src), ("dst", link.dst)):
                if ref not in known:
                    self.broken_endpoints.append(
                        BrokenEndpoint(link_id=link.id, role=role, missing_id=ref)  # type: ignore[arg-type]
                    )

    # -- basic accessors -------------------------------------------------

    def exists(self, component_id: str) -> bool:
        return component_id in self.design.components

    def out_links(self, component_id: str) -> list[Link]:
        return self.outgoing.get(component_id, [])

    def in_links(self, component_id: str) -> list[Link]:
        return self.incoming.get(component_id, [])

    def link_count(self, component_id: str) -> int:
        """Number of **distinct** links touching a component.

        Deliberately not the graph-theoretic degree: a self-loop is one link,
        so ``r0`` reports 7 and not 8. ``bandwidth_balance`` makes the opposite
        choice and counts a self-loop on both sides, because there the question
        is capacity consumed, not links attached.
        """
        return len(
            {link.id for link in self.out_links(component_id)}
            | {link.id for link in self.in_links(component_id)}
        )

    def unconnected_components(self) -> list[str]:
        """Component ids no *resolvable* link touches."""
        return sorted(
            cid for cid in self.design.components if self.link_count(cid) == 0
        )

    # -- topology queries ------------------------------------------------

    def neighbors(self, component_id: str, direction: Direction = "both") -> dict[str, Any]:
        """Peers of a component, with the link that connects them.

        ``peer_exists`` is False when the link points at an unknown id; the
        edge is still reported rather than hidden.
        """
        out: list[dict[str, Any]] = []
        inc: list[dict[str, Any]] = []
        if direction in ("out", "both"):
            out = [self._edge(link, link.dst, "out") for link in self.out_links(component_id)]
        if direction in ("in", "both"):
            inc = [self._edge(link, link.src, "in") for link in self.in_links(component_id)]
        return {"component_id": component_id, "outgoing": out, "incoming": inc}

    def _edge(self, link: Link, peer_id: str, direction: str) -> dict[str, Any]:
        peer = self.design.components.get(peer_id)
        return {
            "direction": direction,
            "link_id": link.id,
            "peer_id": peer_id,
            "peer_exists": peer is not None,
            "peer_kind": peer.kind if peer else None,
            "peer_name": peer.name if peer else None,
            "link_properties": dict(link.properties),
        }

    def find_path(
        self, src: str, dst: str, max_hops: int = 8
    ) -> dict[str, Any]:
        """Shortest directed path src -> dst (BFS, so fewest hops).

        Only traverses edges whose endpoints exist, and never revisits a node,
        so Orion's ``L_loop`` self-loop cannot make this spin.
        """
        if src == dst:
            return {"found": True, "hops": 0, "components": [src], "links": []}
        # queue holds (component_id, [link_ids], [component_ids])
        queue: deque[tuple[str, list[str], list[str]]] = deque([(src, [], [src])])
        seen = {src}
        while queue:
            node, links, path = queue.popleft()
            if len(links) >= max_hops:
                continue
            for link in self.out_links(node):
                peer = link.dst
                if peer not in self.design.components or peer in seen:
                    continue
                if peer == dst:
                    return {
                        "found": True,
                        "hops": len(links) + 1,
                        "components": path + [peer],
                        "links": links + [link.id],
                    }
                seen.add(peer)
                queue.append((peer, links + [link.id], path + [peer]))
        return {
            "found": False,
            "hops": None,
            "components": [],
            "links": [],
            "reason": f"No directed path from {src} to {dst} within {max_hops} hops",
        }

    # -- quantitative view ----------------------------------------------

    def bandwidth_balance(self, component_id: str) -> dict[str, Any]:
        """Sum of inbound vs outbound ``bandwidth_mbps`` around a component.

        Self-loops are counted on both sides (they consume the node's
        switching capacity twice), and links with a non-numeric bandwidth are
        reported separately instead of being silently treated as zero.
        """
        ingress = 0.0
        egress = 0.0
        unmeasured: list[str] = []
        for link in self.in_links(component_id):
            value = as_float(link.properties.get("bandwidth_mbps"))
            if value is None:
                unmeasured.append(link.id)
            else:
                ingress += value
        for link in self.out_links(component_id):
            value = as_float(link.properties.get("bandwidth_mbps"))
            if value is None:
                unmeasured.append(link.id)
            else:
                egress += value
        return {
            "component_id": component_id,
            "ingress_mbps": ingress,
            "egress_mbps": egress,
            "oversubscription_ratio": round(ingress / egress, 4) if egress else None,
            "links_without_numeric_bandwidth": sorted(set(unmeasured)),
        }

    def clock_domain(self, component_id: str) -> str | None:
        comp = self.design.components.get(component_id)
        if comp is None:
            return None
        value = comp.properties.get("clock_domain")
        return value if isinstance(value, str) else None


def build_graph(design: Design) -> DesignGraph:
    return DesignGraph(design=design)


def iter_component_ids(design: Design) -> Iterable[str]:
    return sorted(design.components)
