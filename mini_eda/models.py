from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Component:
    id: str
    kind: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "properties": dict(self.properties),
        }


@dataclass
class Link:
    id: str
    src: str
    dst: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "src": self.src,
            "dst": self.dst,
            "properties": dict(self.properties),
        }


@dataclass
class Issue:
    code: str
    message: str
    element_id: str | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "element_id": self.element_id,
            "severity": self.severity,
        }


@dataclass
class Design:
    name: str
    version: str
    description: str
    components: dict[str, Component]
    links: dict[str, Link]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "components": [c.to_dict() for c in self.components.values()],
            "links": [link.to_dict() for link in self.links.values()],
            "notes": list(self.notes),
        }
