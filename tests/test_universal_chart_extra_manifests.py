"""Extra manifest rendering tests for universal-chart."""

from __future__ import annotations

import subprocess

from .chart_test_utils import get_manifest, load_manifests, render_chart
from .universal_chart_test_utils import CHART

VALUES_FILE = CHART.fixtures_dir / "extra-manifests-values.yaml"


def test_object_extra_manifest_renders_as_separate_document(
    helm_runner,
) -> None:
    """Render an object-form extra manifest as valid YAML."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values_files=[VALUES_FILE],
    )
    manifests = load_manifests(rendered)
    config_map = get_manifest(
        manifests,
        "ConfigMap",
        "universal-chart-extra",
    )
    second_config_map = get_manifest(
        manifests,
        "ConfigMap",
        "universal-chart-extra-second",
    )

    assert config_map["data"] == {"message": "hello"}
    assert second_config_map["data"] == {"message": "goodbye"}


def test_object_extra_manifest_passes_helm_lint(helm_runner) -> None:
    """Keep the document separator distinct during Helm linting."""

    command = [
        helm_runner.helm_binary_path,
        "lint",
        str(CHART.chart_dir),
        "--values",
        str(VALUES_FILE),
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
