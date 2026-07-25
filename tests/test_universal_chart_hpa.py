"""HorizontalPodAutoscaler tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import get_manifest, render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import (
    CHART,
    render_manifest,
    render_manifests,
)


def test_hpa_scaling_rule_renders_external_metric_and_recording_rule(
    helm_runner,
) -> None:
    """Wire Prometheus records to HPA external metrics."""

    manifests = render_manifests(
        helm_runner,
        values={
            "prometheusRule": {
                "enabled": True,
                "additionalLabels": {"release": "kube-prometheus-stack"},
            },
            "autoscaling": {
                "enabled": True,
                "minReplicas": 2,
                "maxReplicas": 20,
                "targetCPUUtilizationPercentage": None,
                "behavior": {
                    "scaleDown": {"stabilizationWindowSeconds": 300},
                },
                "hpaScalingRules": [
                    {
                        "name": "myapp_queue_depth",
                        "expr": (
                            "sum by (queue) "
                            '(myapp_queue_depth{namespace="app"})'
                        ),
                        "labels": {
                            "queue": "default",
                            "hpa_metric": "false",
                        },
                        "selector": {"queue": "default"},
                        "target": {
                            "type": "AverageValue",
                            "averageValue": "100",
                        },
                    }
                ],
            },
        },
    )
    hpa = get_manifest(manifests, "HorizontalPodAutoscaler")
    prom_rule = get_manifest(manifests, "PrometheusRule")

    assert hpa["spec"]["minReplicas"] == 2
    assert hpa["spec"]["maxReplicas"] == 20
    assert (
        hpa["spec"]["behavior"]["scaleDown"]["stabilizationWindowSeconds"]
        == 300
    )
    assert hpa["spec"]["metrics"] == [
        {
            "type": "External",
            "external": {
                "metric": {
                    "name": "myapp_queue_depth",
                    "selector": {"matchLabels": {"queue": "default"}},
                },
                "target": {
                    "type": "AverageValue",
                    "averageValue": "100",
                },
            },
        }
    ]
    assert prom_rule["metadata"]["labels"]["release"] == (
        "kube-prometheus-stack"
    )
    group = prom_rule["spec"]["groups"][0]
    assert group["name"] == "universal-chart.hpa-scaling"
    recording_rule = group["rules"][0]
    assert recording_rule["record"] == "myapp_queue_depth"
    assert recording_rule["expr"] == (
        'sum by (queue) (myapp_queue_depth{namespace="app"})'
    )
    assert recording_rule["labels"]["queue"] == "default"
    assert recording_rule["labels"]["hpa_metric"] == "true"


def test_hpa_scaling_rule_supports_value_target(helm_runner) -> None:
    """Use Value targets on the chart-managed HPA."""

    hpa = render_manifest(
        helm_runner,
        "HorizontalPodAutoscaler",
        values={
            "autoscaling": {
                "enabled": True,
                "targetCPUUtilizationPercentage": None,
                "hpaScalingRules": [
                    {
                        "name": "myapp_queue_messages",
                        "expr": 'sum(myapp_queue_messages{queue="critical"})',
                        "target": {"type": "Value", "value": "500"},
                    }
                ],
            }
        },
    )

    assert hpa["spec"]["scaleTargetRef"]["name"] == "universal-chart"
    assert hpa["spec"]["metrics"][0]["external"]["target"] == {
        "type": "Value",
        "value": "500",
    }


def test_hpa_annotations_render_when_enabled(helm_runner) -> None:
    """Add requested annotations to the HPA."""

    hpa = render_manifest(
        helm_runner,
        "HorizontalPodAutoscaler",
        values={
            "autoscaling": {
                "enabled": True,
                "annotations": {"argocd.argoproj.io/sync-wave": "10"},
            }
        },
    )

    assert hpa["metadata"]["annotations"] == {
        "argocd.argoproj.io/sync-wave": "10"
    }


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(
            {
                "autoscaling": {
                    "enabled": True,
                    "hpaScalingRules": [
                        {
                            "name": "myapp_queue_depth",
                            "target": {"averageValue": "100"},
                        }
                    ],
                }
            },
            id="scaling-rule-missing-expr",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "enabled": True,
                    "hpaScalingRules": [
                        {
                            "name": "myapp-queue-depth",
                            "expr": "vector(1)",
                            "target": {"averageValue": "100"},
                        }
                    ],
                }
            },
            id="invalid-metric-name",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "enabled": True,
                    "hpaScalingRules": [
                        {
                            "name": "myapp_queue_depth",
                            "expr": "vector(1)",
                            "labels": {"queue": 1},
                            "target": {"averageValue": "100"},
                        }
                    ],
                }
            },
            id="scaling-rule-label-is-not-string",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "enabled": True,
                    "hpaScalingRules": [
                        {
                            "name": "myapp_queue_depth",
                            "expr": "vector(1)",
                            "target": {
                                "type": "Utilization",
                                "averageValue": "100",
                            },
                        }
                    ],
                }
            },
            id="invalid-target-type",
        ),
    ],
)
def test_hpa_schema_rejects_invalid_values(
    helm_runner,
    values: dict[str, Any],
) -> None:
    """Reject malformed HPA scaling rules."""

    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values=values)
