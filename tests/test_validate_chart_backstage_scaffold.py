"""Tests for chart Backstage scaffold validation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "validate_chart_backstage_scaffold.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_chart_backstage_scaffold", MODULE_PATH
)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_chart(chart_dir: Path) -> None:
    """Create a minimal chart with docs scaffolding."""

    (chart_dir / "docs").mkdir(parents=True)
    (chart_dir / "Chart.yaml").write_text("apiVersion: v2\nname: sample\n")
    (chart_dir / "catalog-info.yaml").write_text(
        "annotations:\n  backstage.io/techdocs-ref: dir:.\n"
    )
    (chart_dir / "mkdocs.yml").write_text(
        "nav:\n  - Generated Reference: reference.md\n"
    )
    (chart_dir / "docs" / "index.md").write_text("# Sample\n")
    (chart_dir / "README.md").write_text("# Reference\n")
    (chart_dir / "docs" / "reference.md").symlink_to("../README.md")


def test_validate_chart_accepts_complete_scaffold(
    tmp_path, monkeypatch
) -> None:
    """A fully scaffolded chart should pass."""

    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    chart_dir = charts_dir / "sample"
    chart_dir.mkdir()
    write_chart(chart_dir)
    root_catalog = tmp_path / "catalog-info.yaml"
    root_catalog.write_text("  - ./charts/sample/catalog-info.yaml\n")

    monkeypatch.setattr(MODULE, "CHARTS_DIR", charts_dir)
    monkeypatch.setattr(MODULE, "ROOT_CATALOG", root_catalog)

    assert MODULE.main() == 0


def test_validate_chart_reports_missing_catalog_target(
    tmp_path, monkeypatch, capsys
) -> None:
    """Missing root catalog targets should fail validation."""

    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    chart_dir = charts_dir / "sample"
    chart_dir.mkdir()
    write_chart(chart_dir)
    root_catalog = tmp_path / "catalog-info.yaml"
    root_catalog.write_text("spec:\n  targets: []\n")

    monkeypatch.setattr(MODULE, "CHARTS_DIR", charts_dir)
    monkeypatch.setattr(MODULE, "ROOT_CATALOG", root_catalog)

    assert MODULE.main() == 1
    captured = capsys.readouterr()
    assert (
        "Root catalog-info.yaml is missing ./charts/sample/catalog-info.yaml"
        in captured.out
    )
