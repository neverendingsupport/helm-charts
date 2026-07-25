"""PrometheusRule tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifest


def test_prometheus_rule_renders_rule_strings_verbatim(helm_runner) -> None:
    """Keep PromQL and template strings unchanged."""

    prom_rule = render_manifest(
        helm_runner,
        "PrometheusRule",
        values={
            "prometheusRule": {
                "enabled": True,
                "annotations": {"example.com/source": "chart"},
                "additionalLabels": {"team": "example"},
                "defaultRuleLabels": {
                    "slack_channel": "#alert-example",
                    "team": "example",
                },
                "rules": [
                    {
                        "alert": "ApplicationDown",
                        "expr": 'up{job="universal-chart"} == 0',
                        "for": "2m",
                        "labels": {"severity": "warning"},
                        "annotations": {
                            "summary": "App {{ $labels.job }} down",
                            "description": (
                                "App {{ $labels.job }} has no healthy targets"
                            ),
                        },
                    }
                ],
            }
        },
    )

    assert prom_rule["metadata"]["name"] == "universal-chart"
    assert prom_rule["metadata"]["labels"]["team"] == "example"
    assert prom_rule["metadata"]["annotations"]["example.com/source"] == "chart"
    rule = prom_rule["spec"]["groups"][0]["rules"][0]
    assert rule["expr"] == 'up{job="universal-chart"} == 0'
    assert rule["labels"]["severity"] == "warning"
    assert rule["labels"]["slack_channel"] == "#alert-example"
    assert rule["labels"]["team"] == "example"
    assert rule["annotations"]["summary"] == "App {{ $labels.job }} down"


def test_prometheus_rule_supports_explicit_groups(helm_runner) -> None:
    """Render explicit groups before simple fallback rules."""

    prom_rule = render_manifest(
        helm_runner,
        "PrometheusRule",
        values={
            "prometheusRule": {
                "enabled": True,
                "groups": [
                    {
                        "name": "eol-api.rules",
                        "interval": "1m",
                        "rules": [
                            {
                                "alert": "ApplicationDown",
                                "expr": 'up{job="eol-api"} == 0',
                                "for": "5m",
                                "labels": {"severity": "warning"},
                                "annotations": {"summary": "eol-api is down"},
                            }
                        ],
                    }
                ],
                "rules": [
                    {
                        "alert": "IgnoredFallbackRule",
                        "expr": "vector(1)",
                    }
                ],
            }
        },
    )

    group = prom_rule["spec"]["groups"][0]
    assert group["name"] == "eol-api.rules"
    assert group["interval"] == "1m"
    assert group["rules"][0]["alert"] == "ApplicationDown"
    assert group["rules"][0]["expr"] == 'up{job="eol-api"} == 0'


def test_prometheus_rule_merges_default_labels_into_groups(
    helm_runner,
) -> None:
    """Merge default labels while preserving per-rule overrides."""

    prom_rule = render_manifest(
        helm_runner,
        "PrometheusRule",
        values={
            "prometheusRule": {
                "enabled": True,
                "defaultRuleLabels": {
                    "application": "eol-api",
                    "group": "eol",
                    "slack_channel": "#alert-eol",
                    "team": "data-integrations",
                },
                "groups": [
                    {
                        "name": "eol-api.rules",
                        "rules": [
                            {
                                "alert": "ApplicationDown",
                                "expr": 'up{job="eol-api"} == 0',
                                "labels": {
                                    "severity": "warning",
                                    "slack_channel": "#alert-special",
                                },
                            }
                        ],
                    }
                ],
            }
        },
    )
    rule = prom_rule["spec"]["groups"][0]["rules"][0]

    assert rule["labels"]["application"] == "eol-api"
    assert rule["labels"]["group"] == "eol"
    assert rule["labels"]["team"] == "data-integrations"
    assert rule["labels"]["severity"] == "warning"
    assert rule["labels"]["slack_channel"] == "#alert-special"


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(
            {
                "prometheusRule": {
                    "enabled": True,
                    "rules": [{"alert": "ApplicationDown"}],
                }
            },
            id="rule-missing-expr",
        ),
        pytest.param(
            {
                "prometheusRule": {
                    "enabled": True,
                    "rules": [
                        {
                            "alert": "ApplicationDown",
                            "expr": 'up{job="universal-chart"} == 0',
                            "labels": {"severity": 1},
                        }
                    ],
                }
            },
            id="rule-label-is-not-string",
        ),
        pytest.param(
            {
                "prometheusRule": {
                    "enabled": True,
                    "groups": [
                        {
                            "rules": [
                                {
                                    "alert": "ApplicationDown",
                                    "expr": 'up{job="universal-chart"} == 0',
                                }
                            ]
                        }
                    ],
                }
            },
            id="group-missing-name",
        ),
    ],
)
def test_prometheus_rule_schema_rejects_invalid_values(
    helm_runner,
    values: dict[str, Any],
) -> None:
    """Reject malformed PrometheusRule values."""

    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values=values)
