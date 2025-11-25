"""Shared helpers for chart-based pytest suites."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping

import yaml

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from pytest_helm_charts.giantswarm.helm import HelmRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
CHARTS_DIR = REPO_ROOT / "charts"
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures"


@dataclass(frozen=True)
class ChartContext:
    """Metadata about a chart under test."""

    chart_name: str
    release_name: str | None = None

    @property
    def chart_dir(self) -> Path:
        """Return the path to the chart directory under test."""
        return CHARTS_DIR / self.chart_name

    @property
    def fixtures_dir(self) -> Path:
        """Return the path to this chart's test fixtures directory."""
        return FIXTURES_ROOT / self.chart_name

    @property
    def default_values_file(self) -> Path:
        """Return the default values file used in most tests."""
        return self.fixtures_dir / "minimal-values.yaml"

    @property
    def release(self) -> str:
        """Return the Helm release name used when rendering."""
        return self.release_name or self.chart_name


def render_chart(
    helm_runner: "HelmRunner",
    chart: ChartContext,
    *,
    values_files: Iterable[Path] | None = None,
    values: Mapping[str, Any] | None = None,
) -> str:
    """Render the requested chart and return the YAML output."""

    files = list(values_files or (chart.default_values_file,))
    str_files = [str(path) for path in files]
    return helm_runner.template(
        name=chart.release,
        chart=str(chart.chart_dir),
        values_files=str_files,
        values=values,
    )


def assert_matches_golden(rendered: str, golden_file: Path) -> None:
    """Compare rendered output to a stored golden manifest."""

    expected = golden_file.read_text()
    assert rendered.strip() + "\n" == expected


def load_manifests(rendered: str) -> list[dict[str, Any]]:
    """Convert Helm output into a list of manifest dictionaries."""

    documents = yaml.safe_load_all(rendered)
    return [doc for doc in documents if doc]


def get_manifest(manifests: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    """Return the manifest with the requested kind."""

    for manifest in manifests:
        if manifest.get("kind") == kind:
            return manifest
    raise AssertionError(f"Manifest kind {kind} not found")


def get_primary_container(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the first container spec from the deployment manifest."""

    deployment = get_manifest(manifests, "Deployment")
    return deployment["spec"]["template"]["spec"]["containers"][0]


__all__ = [
    "ChartContext",
    "assert_matches_golden",
    "get_manifest",
    "get_primary_container",
    "load_manifests",
    "render_chart",
]
