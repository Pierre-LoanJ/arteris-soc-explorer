"""Shared fixtures.

Every test that can write works on a **copy** of the design in ``tmp_path``,
following the convention already used by ``tests/test_eda_basic.py``: the
committed fixture is a shared resource and a test suite that dirties it is a
test suite you stop trusting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soc_explorer.adapter import SocExplorerAdapter
from soc_explorer.tools import SocExplorer

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data" / "designs" / "orion_soc.json"


@pytest.fixture()
def design_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "orion_soc.json"
    copy.write_text(DESIGN.read_text(encoding="utf-8"), encoding="utf-8")
    return copy


@pytest.fixture()
def explorer(design_copy: Path) -> SocExplorer:
    return SocExplorer(design_copy)


@pytest.fixture()
def adapter(design_copy: Path) -> SocExplorerAdapter:
    return SocExplorerAdapter(design_copy)


@pytest.fixture()
def design_writer(tmp_path: Path):
    """Build a small design file on the fly, for checks Orion cannot trigger."""

    def _write(name: str, payload: dict) -> Path:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    return _write
