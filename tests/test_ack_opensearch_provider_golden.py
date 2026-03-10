"""Golden file tests for the ACK OpenSearch provider chart."""

from __future__ import annotations

from pathlib import Path

import pytest

from .chart_test_utils import ChartContext, assert_matches_golden, render_chart

CHART = ChartContext("ack-opensearch-provider")


def discover_golden_pairs() -> list[tuple[Path, Path]]:
    """Return (values_file, golden_file) pairs for the chart."""

    pairs: list[tuple[Path, Path]] = []
    fixtures_dir = CHART.fixtures_dir
    for values_file in sorted(fixtures_dir.glob("*-values.yaml")):
        golden_file = values_file.with_suffix(".golden.yaml")
        if golden_file.exists():
            pairs.append((values_file, golden_file))
    return pairs


@pytest.mark.parametrize("fixture_pair", discover_golden_pairs())
def test_golden_renderings(
    helm_runner, fixture_pair: tuple[Path, Path]
) -> None:
    """Verify the rendered manifest matches the stored golden output."""

    values_file, golden_file = fixture_pair
    rendered = render_chart(helm_runner, CHART, values_files=[values_file])
    assert_matches_golden(rendered, golden_file)
