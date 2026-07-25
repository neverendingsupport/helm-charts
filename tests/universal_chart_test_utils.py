"""Shared helpers for universal-chart tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    load_manifests,
    render_chart,
)

if TYPE_CHECKING:
    from pytest_helm_charts.giantswarm.helm import HelmRunner

CHART = ChartContext("universal-chart")


def render_manifests(
    helm_runner: HelmRunner,
    *,
    values: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Render the chart and parse its manifests."""

    rendered = render_chart(helm_runner, CHART, values=values)
    return load_manifests(rendered)


def render_manifest(
    helm_runner: HelmRunner,
    kind: str,
    *,
    values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Render the chart and return one manifest by kind."""

    return get_manifest(
        render_manifests(helm_runner, values=values),
        kind,
    )


__all__ = ["CHART", "render_manifest", "render_manifests"]
