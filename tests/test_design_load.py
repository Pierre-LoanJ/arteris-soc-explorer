import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data" / "designs" / "orion_soc.json"


def test_design_json_is_well_formed() -> None:
    data = json.loads(DESIGN.read_text(encoding="utf-8"))
    assert "components" in data and "links" in data
    ids = [c["id"] for c in data["components"]]
    assert len(ids) == len(set(ids))
    link_ids = [link["id"] for link in data["links"]]
    assert len(link_ids) == len(set(link_ids))
