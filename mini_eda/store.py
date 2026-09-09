from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import ValidationError
from .models import Component, Design, Link


class DesignStore:
    """JSON file-backed design store.

    Note: save() overwrites the file in place. There is no backup, lock,
    or transactional write. Callers are responsible for any higher-level
    safety policy.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._design: Design | None = None

    @property
    def design(self) -> Design:
        if self._design is None:
            raise ValidationError("No design loaded")
        return self._design

    def load(self) -> Design:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        components = {
            c["id"]: Component(
                id=c["id"],
                kind=c["kind"],
                name=c["name"],
                properties=dict(c.get("properties") or {}),
            )
            for c in raw.get("components", [])
        }
        links = {
            link["id"]: Link(
                id=link["id"],
                src=link["src"],
                dst=link["dst"],
                properties=dict(link.get("properties") or {}),
            )
            for link in raw.get("links", [])
        }
        self._design = Design(
            name=raw.get("name", self.path.stem),
            version=str(raw.get("version", "0")),
            description=raw.get("description", ""),
            components=components,
            links=links,
            notes=list(raw.get("notes") or []),
        )
        return self._design

    def save(self) -> None:
        """Persist the current design, overwriting the source file."""
        design = self.design
        payload: dict[str, Any] = design.to_dict()
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
