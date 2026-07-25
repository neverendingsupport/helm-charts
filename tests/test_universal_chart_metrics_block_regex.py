"""Regex Ingress metrics-block tests for universal-chart."""

from __future__ import annotations

import pytest

from .chart_test_utils import render_chart
from .conftest import HelmTemplateError
from .universal_chart_metrics_block_test_utils import (
    ingresses_by_name,
    regex_ingress_values,
)
from .universal_chart_test_utils import CHART, render_manifests


def test_metrics_block_ingress_rejects_rewrite_ingress(
    helm_runner,
) -> None:
    """Reject rewrite rules unless regex blocking is explicit."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values=regex_ingress_values(),
        )


def test_metrics_block_ingress_renders_for_explicit_regex(
    helm_runner,
) -> None:
    """Render a specific metrics regex when the caller opts in."""

    values = regex_ingress_values(
        block_external_ingress={
            "allowRegexIngress": True,
            "path": "/eol/api/metrics(/|$)(.*)",
            "pathType": "ImplementationSpecific",
        }
    )
    ingresses = ingresses_by_name(render_manifests(helm_runner, values=values))
    block_path = ingresses[f"{CHART.release}-metrics-block"]["spec"]["rules"][
        0
    ]["http"]["paths"][0]

    assert block_path["path"] == "/eol/api/metrics(/|$)(.*)"
    assert block_path["pathType"] == "ImplementationSpecific"


def test_regex_mode_requires_explicit_block_path(helm_runner) -> None:
    """Require the public metrics regex in regex mode."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values=regex_ingress_values(
                block_external_ingress={"allowRegexIngress": True},
            ),
        )


def test_regex_mode_requires_implementation_specific_path(
    helm_runner,
) -> None:
    """Require ImplementationSpecific for regex block paths."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values=regex_ingress_values(
                block_external_ingress={
                    "allowRegexIngress": True,
                    "path": "/eol/api/metrics(/|$)(.*)",
                },
            ),
        )


def test_metrics_block_ingress_rejects_case_variant_regex(
    helm_runner,
) -> None:
    """Reject nginx use-regex values other than lowercase true."""

    values = regex_ingress_values()
    values["ingress"]["annotations"][
        "nginx.ingress.kubernetes.io/use-regex"
    ] = "True"

    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values=values)
