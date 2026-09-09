from pathlib import Path

import pytest

from mini_eda import MiniEda, NotFoundError


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data" / "designs" / "orion_soc.json"


@pytest.fixture()
def eda(tmp_path: Path) -> MiniEda:
    # Work on a copy so tests never mutate the shared fixture permanently.
    copy = tmp_path / "orion_soc.json"
    copy.write_text(DESIGN.read_text(encoding="utf-8"), encoding="utf-8")
    return MiniEda(copy)


def test_load_design(eda: MiniEda) -> None:
    assert eda.design.name == "orion_soc"
    assert len(eda.list_components()) >= 5
    assert len(eda.list_links()) >= 5


def test_get_component(eda: MiniEda) -> None:
    cpu = eda.get_component("cpu0")
    assert cpu.kind == "initiator"
    assert cpu.properties.get("protocol") == "AXI4"


def test_get_component_missing(eda: MiniEda) -> None:
    with pytest.raises(NotFoundError):
        eda.get_component("does_not_exist")


def test_update_property_and_reread(eda: MiniEda) -> None:
    eda.update_property("cpu0", "qos", "low")
    assert eda.get_component("cpu0").properties["qos"] == "low"
    eda.reload()
    assert eda.get_component("cpu0").properties["qos"] == "low"


def test_validate_returns_list(eda: MiniEda) -> None:
    issues = eda.validate()
    assert isinstance(issues, list)


def test_export_report_text(eda: MiniEda) -> None:
    report = eda.export_report("text")
    assert isinstance(report, str)
    assert "orion_soc" in report
