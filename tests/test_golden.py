"""Golden file tests for every chart with fixtures.

Charts are discovered automatically: any directory under tests/fixtures/
that matches a chart in charts/ contributes one test per
``*-values.yaml`` / ``*-values.golden.yaml`` pair.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .chart_test_utils import ChartContext, assert_matches_golden, render_chart
from .fixture_layout import golden_for, iter_fixture_dirs, iter_values_fixtures


def discover_golden_pairs() -> list[tuple[str, Path, Path]]:
    """Return (chart_name, values_file, golden_file) for every fixture."""

    pairs: list[tuple[str, Path, Path]] = []
    for fixture_dir in iter_fixture_dirs():
        for values_file in iter_values_fixtures(fixture_dir):
            golden_file = golden_for(values_file)
            if golden_file.exists():
                pairs.append((fixture_dir.name, values_file, golden_file))
    return pairs


def _golden_id(pair: tuple[str, Path, Path]) -> str:
    chart_name, values_file, _ = pair
    fixture = values_file.stem.removesuffix("-values")
    return f"{chart_name}/{fixture}"


@pytest.mark.parametrize(
    "fixture_pair",
    discover_golden_pairs(),
    ids=_golden_id,
)
def test_golden_renderings(
    helm_runner,
    fixture_pair: tuple[str, Path, Path],
) -> None:
    """Verify the rendered manifests match the stored golden output."""

    chart_name, values_file, golden_file = fixture_pair
    rendered = render_chart(
        helm_runner,
        ChartContext(chart_name),
        values_files=[values_file],
    )
    assert_matches_golden(rendered, golden_file)
