"""HorizontalPodAutoscaler tests for universal-chart."""

from __future__ import annotations

from .chart_test_utils import get_manifest
from .universal_chart_test_utils import (
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
                "metrics": [],
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
            },
            "resources": {"requests": {"cpu": "100m"}},
        },
    )

    assert hpa["metadata"]["annotations"] == {
        "argocd.argoproj.io/sync-wave": "10"
    }


def test_autoscaling_uses_native_autoscaling_v2_metrics(helm_runner) -> None:
    """Pass every stable autoscaling/v2 MetricSpec source through unchanged."""

    metrics = [
        {
            "type": "Resource",
            "resource": {
                "name": "cpu",
                "target": {
                    "type": "Utilization",
                    "averageUtilization": 70,
                },
            },
        },
        {
            "type": "ContainerResource",
            "containerResource": {
                "name": "memory",
                "container": "universal-chart",
                "target": {
                    "type": "AverageValue",
                    "averageValue": "512Mi",
                },
            },
        },
        {
            "type": "External",
            "external": {
                "metric": {
                    "name": "queue_depth",
                    "selector": {"matchLabels": {"queue": "critical"}},
                },
                "target": {"type": "Value", "value": "100"},
            },
        },
        {
            "type": "Object",
            "object": {
                "describedObject": {
                    "apiVersion": "networking.k8s.io/v1",
                    "kind": "Ingress",
                    "name": "example",
                },
                "metric": {"name": "requests_per_second"},
                "target": {"type": "Value", "value": "1k"},
            },
        },
        {
            "type": "Pods",
            "pods": {
                "metric": {"name": "packets_per_second"},
                "target": {"type": "AverageValue", "averageValue": "1k"},
            },
        },
    ]
    hpa = render_manifest(
        helm_runner,
        "HorizontalPodAutoscaler",
        values={
            "autoscaling": {
                "enabled": True,
                "minReplicas": 2,
                "maxReplicas": 12,
                "metrics": metrics,
            },
            "resources": {"requests": {"cpu": "100m"}},
        },
    )

    assert hpa["apiVersion"] == "autoscaling/v2"
    assert hpa["spec"]["metrics"] == metrics


def test_native_metrics_replace_percentage_resource_targets(
    helm_runner,
) -> None:
    """Use an explicitly supplied native metrics list instead of legacy CPU."""

    external_metric = {
        "type": "External",
        "external": {
            "metric": {"name": "queue_depth"},
            "target": {"type": "AverageValue", "averageValue": "20"},
        },
    }
    hpa = render_manifest(
        helm_runner,
        "HorizontalPodAutoscaler",
        values={
            "autoscaling": {
                "enabled": True,
                "targetCPUUtilizationPercentage": 80,
                "metrics": [external_metric],
            }
        },
    )

    assert hpa["spec"]["metrics"] == [external_metric]


def test_autoscaling_disabled_keeps_fixed_replicas(helm_runner) -> None:
    """Keep fixed replicas when HPA autoscaling is disabled."""

    manifests = render_manifests(
        helm_runner,
        values={
            "replicaCount": 3,
            "autoscaling": {
                "enabled": False,
                "metrics": [],
            },
        },
    )

    assert all(item["kind"] != "HorizontalPodAutoscaler" for item in manifests)
    deployment = get_manifest(manifests, "Deployment")
    assert deployment["spec"]["replicas"] == 3


def test_hpa_scaling_rules_append_to_native_metrics(helm_runner) -> None:
    """Append generated Prometheus metrics to native metrics."""

    native_metric = {
        "type": "External",
        "external": {
            "metric": {"name": "native_queue_depth"},
            "target": {"type": "Value", "value": "50"},
        },
    }
    hpa = render_manifest(
        helm_runner,
        "HorizontalPodAutoscaler",
        values={
            "autoscaling": {
                "enabled": True,
                "targetCPUUtilizationPercentage": None,
                "metrics": [native_metric],
                "hpaScalingRules": [
                    {
                        "name": "recorded_queue_depth",
                        "expr": "vector(2)",
                        "target": {"averageValue": "2"},
                    }
                ],
            }
        },
    )

    names = [
        metric["external"]["metric"]["name"]
        for metric in hpa["spec"]["metrics"]
    ]
    assert names == [
        "native_queue_depth",
        "recorded_queue_depth",
    ]
