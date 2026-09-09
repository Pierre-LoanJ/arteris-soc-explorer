"""Ranked search over a design.

Split out of ``tools.py`` because the ranking *is* the feature: the exercise
warns that "search quality matters", and ``MiniEda.search`` is a case-sensitive
substring scan over ids, names and endpoints that cannot tell the router ``r0``
from the ``r0`` inside ``ddr0``, and never looks at properties (so ``AXI4``
finds nothing at all).

The model here is deliberately simple and inspectable rather than clever:
each field is classified as ``exact`` / ``prefix`` / ``substring``, each field
carries a weight, a hit scores as its best match, and the payload reports the
matches so a caller can see *why* something ranked where it did. The weights
are hand-tuned judgment, not a learned model — which is exactly why they are
exposed rather than hidden.
"""

from __future__ import annotations

from typing import Any, Callable

from mini_eda.models import Component, Design, Link

from . import schemas as S

#: Field weights. Ordering intent: an exact id beats a display name, which
#: beats a kind, which beats a link merely referencing the id, which beats a
#: property value.
ID_WEIGHTS = {"exact": 1.0, "prefix": 0.8, "substring": 0.6}
NAME_WEIGHTS = {"exact": 0.95, "prefix": 0.7, "substring": 0.65}
KIND_WEIGHTS = {"exact": 0.7, "prefix": 0.45, "substring": 0.45}
ENDPOINT_WEIGHTS = {"exact": 0.55, "prefix": 0.4, "substring": 0.35}
PROP_WEIGHTS = {"exact": 0.5, "prefix": 0.3, "substring": 0.3}


def search_design(
    design: Design,
    inp: S.SearchInput,
    component_payload: Callable[[Component], dict[str, Any]],
) -> dict[str, Any]:
    """Rank every element against ``inp.query``.

    ``component_payload`` lets the caller decide how much of a component to
    embed in a hit (``tools`` passes the enriched row carrying ``link_count``)
    without this module having to know about the topology index.
    """
    hits: list[dict[str, Any]] = []
    if inp.types in ("all", "component"):
        for comp in design.components.values():
            matches = match_component(comp, inp)
            if matches:
                hits.append(_hit("component", comp.id, comp.name, matches, component_payload(comp)))
    if inp.types in ("all", "link"):
        for link in design.links.values():
            matches = match_link(link, inp)
            if matches:
                hits.append(_hit("link", link.id, f"{link.src} -> {link.dst}", matches, link.to_dict()))

    hits.sort(key=lambda hit: (-hit["score"], hit["id"]))
    shown = hits[: inp.limit]
    return {
        "query": inp.query,
        "case_sensitive": inp.case_sensitive,
        "count": len(shown),
        "total_matching": len(hits),
        "truncated": len(hits) > len(shown),
        "hits": shown,
    }


def _hit(
    element_type: str,
    element_id: str,
    label: str,
    matches: list[dict[str, Any]],
    element: dict[str, Any],
) -> dict[str, Any]:
    matches.sort(key=lambda m: -m["score"])
    return {
        "type": element_type,
        "id": element_id,
        "label": label,
        "score": matches[0]["score"],
        "matched_fields": matches,
        "element": element,
    }


def _fold(value: str, case_sensitive: bool) -> str:
    return value if case_sensitive else value.lower()


def _text_match(field: str, value: str, query: str, case_sensitive: bool, weights: dict[str, float]) -> dict[str, Any] | None:
    """Classify how ``value`` matches ``query``: exact > prefix > substring."""
    haystack, needle = _fold(value, case_sensitive), _fold(query, case_sensitive)
    if haystack == needle:
        kind, score = "exact", weights["exact"]
    elif haystack.startswith(needle):
        kind, score = "prefix", weights["prefix"]
    elif needle in haystack:
        kind, score = "substring", weights["substring"]
    else:
        return None
    return {"field": field, "value": value, "match": kind, "score": score}


def match_properties(properties: dict[str, Any], inp: S.SearchInput) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if not inp.search_properties:
        return matches
    for key, value in properties.items():
        hit = _text_match(f"properties.{key}", str(value), inp.query, inp.case_sensitive, PROP_WEIGHTS)
        if hit:
            matches.append(hit)
        key_hit = _text_match("property_key", key, inp.query, inp.case_sensitive, PROP_WEIGHTS)
        if key_hit:
            matches.append(key_hit)
    return matches


def match_component(comp: Component, inp: S.SearchInput) -> list[dict[str, Any]]:
    matches = [
        hit
        for hit in (
            _text_match("id", comp.id, inp.query, inp.case_sensitive, ID_WEIGHTS),
            _text_match("name", comp.name, inp.query, inp.case_sensitive, NAME_WEIGHTS),
            _text_match("kind", comp.kind, inp.query, inp.case_sensitive, KIND_WEIGHTS),
        )
        if hit
    ]
    return matches + match_properties(comp.properties, inp)


def match_link(link: Link, inp: S.SearchInput) -> list[dict[str, Any]]:
    matches = [
        hit
        for hit in (
            _text_match("id", link.id, inp.query, inp.case_sensitive, ID_WEIGHTS),
            _text_match("src", link.src, inp.query, inp.case_sensitive, ENDPOINT_WEIGHTS),
            _text_match("dst", link.dst, inp.query, inp.case_sensitive, ENDPOINT_WEIGHTS),
        )
        if hit
    ]
    return matches + match_properties(link.properties, inp)


