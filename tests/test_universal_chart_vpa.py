"""VerticalPodAutoscaler tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import (
    CHART,
    render_manifest,
    render_manifests,
)


def test_vpa_is_absent_by_default(helm_runner) -> None:
    """Do not require VPA CRDs for workloads that have not opted in."""

    manifests = render_manifests(helm_runner)

    assert all(item["kind"] != "VerticalPodAutoscaler" for item in manifests)


def test_vpa_off_renders_safe_recommendation_policy(helm_runner) -> None:
    """Create recommendation-only VPA with bounded resource ownership."""

    vpa = render_manifest(
        helm_runner,
        "VerticalPodAutoscaler",
        values={
            "autoscaling": {
                "vertical": {
                    "enabled": True,
                    "annotations": {"argocd.argoproj.io/sync-wave": "10"},
                }
            }
        },
    )

    assert vpa["apiVersion"] == "autoscaling.k8s.io/v1"
    assert vpa["metadata"]["annotations"] == {
        "argocd.argoproj.io/sync-wave": "10"
    }
    assert vpa["spec"]["targetRef"] == {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "name": "universal-chart",
    }
    assert vpa["spec"]["updatePolicy"] == {
        "updateMode": "Off",
        "minReplicas": 2,
    }
    assert vpa["spec"]["resourcePolicy"]["containerPolicies"] == [
        {
            "containerName": "*",
            "mode": "Auto",
            "controlledResources": ["cpu", "memory"],
            "controlledValues": "RequestsOnly",
            "minAllowed": {},
            "maxAllowed": {},
        }
    ]


@pytest.mark.parametrize("mode", ["Initial", "Recreate", "InPlaceOrRecreate"])
def test_vpa_active_modes_render_with_explicit_ceilings(
    helm_runner,
    mode: str,
) -> None:
    """Render every supported mutating mode when resource ceilings are set."""

    policies = [
        {
            "containerName": "*",
            "mode": "Auto",
            "controlledResources": ["cpu", "memory"],
            "controlledValues": "RequestsOnly",
            "minAllowed": {"cpu": "50m", "memory": "64Mi"},
            "maxAllowed": {"cpu": "2", "memory": "2Gi"},
        }
    ]
    vpa = render_manifest(
        helm_runner,
        "VerticalPodAutoscaler",
        values={
            "autoscaling": {
                "vertical": {
                    "enabled": True,
                    "updatePolicy": {"updateMode": mode, "minReplicas": 3},
                    "resourcePolicy": {"containerPolicies": policies},
                }
            }
        },
    )

    assert vpa["spec"]["updatePolicy"] == {
        "updateMode": mode,
        "minReplicas": 3,
    }
    assert vpa["spec"]["resourcePolicy"]["containerPolicies"] == policies


@pytest.mark.parametrize(
    ("vertical", "message"),
    [
        pytest.param(
            {
                "enabled": True,
                "updatePolicy": {
                    "updateMode": "Recreate",
                    "minReplicas": 2,
                },
                "resourcePolicy": {
                    "containerPolicies": [
                        {
                            "containerName": "*",
                            "mode": "Auto",
                            "controlledResources": ["cpu", "memory"],
                            "controlledValues": "RequestsOnly",
                            "maxAllowed": {"cpu": "1"},
                        }
                    ]
                },
            },
            "requires maxAllowed.memory",
            id="missing-memory-ceiling",
        ),
        pytest.param(
            {
                "enabled": True,
                "updatePolicy": {
                    "updateMode": "Initial",
                    "minReplicas": 2,
                },
                "resourcePolicy": {"containerPolicies": []},
            },
            "require at least one containerPolicy",
            id="active-without-policies",
        ),
        pytest.param(
            {
                "enabled": True,
                "resourcePolicy": {
                    "containerPolicies": [
                        {
                            "containerName": "*",
                            "controlledResources": ["cpu"],
                            "controlledValues": "RequestsOnly",
                        },
                        {
                            "containerName": "*",
                            "controlledResources": ["memory"],
                            "controlledValues": "RequestsOnly",
                        },
                    ]
                },
            },
            "duplicate containerName",
            id="duplicate-container-policy",
        ),
    ],
)
def test_vpa_rejects_unsafe_policy_combinations(
    helm_runner,
    vertical: dict[str, Any],
    message: str,
) -> None:
    """Reject active policies without ownership and safety bounds."""

    with pytest.raises(HelmTemplateError, match=message):
        render_chart(
            helm_runner,
            CHART,
            values={"autoscaling": {"vertical": vertical}},
        )


def test_vpa_schema_rejects_malformed_resource_quantity(helm_runner) -> None:
    """Reject malformed resource bounds before Kubernetes admission."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "autoscaling": {
                    "vertical": {
                        "enabled": True,
                        "updatePolicy": {
                            "updateMode": "Recreate",
                            "minReplicas": 2,
                        },
                        "resourcePolicy": {
                            "containerPolicies": [
                                {
                                    "containerName": "*",
                                    "controlledResources": ["memory"],
                                    "controlledValues": "RequestsOnly",
                                    "maxAllowed": {"memory": "not-a-quantity"},
                                }
                            ]
                        },
                    }
                }
            },
        )


@pytest.mark.parametrize(
    ("resource", "minimum", "maximum"),
    [
        pytest.param("cpu", "1", "500m", id="cpu-decimal-si"),
        pytest.param("memory", "1G", "999M", id="memory-decimal-si"),
        pytest.param("memory", "1Gi", "512Mi", id="memory-binary-si"),
    ],
)
def test_vpa_rejects_inverted_resource_bounds(
    helm_runner,
    resource: str,
    minimum: str,
    maximum: str,
) -> None:
    """Reject bounds that the VPA admission webhook would deny."""

    with pytest.raises(HelmTemplateError, match="cannot exceed"):
        render_chart(
            helm_runner,
            CHART,
            values={
                "autoscaling": {
                    "vertical": {
                        "enabled": True,
                        "updatePolicy": {
                            "updateMode": "Recreate",
                            "minReplicas": 2,
                        },
                        "resourcePolicy": {
                            "containerPolicies": [
                                {
                                    "containerName": "*",
                                    "controlledResources": [resource],
                                    "controlledValues": "RequestsOnly",
                                    "minAllowed": {resource: minimum},
                                    "maxAllowed": {resource: maximum},
                                }
                            ]
                        },
                    }
                }
            },
        )


@pytest.mark.parametrize("mode", ["Auto", "InPlace"])
def test_vpa_schema_rejects_unsupported_update_modes(
    helm_runner,
    mode: str,
) -> None:
    """Reject deprecated or insufficiently portable VPA update modes."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "autoscaling": {
                    "vertical": {
                        "enabled": True,
                        "updatePolicy": {
                            "updateMode": mode,
                            "minReplicas": 2,
                        },
                    }
                }
            },
        )


def test_active_vpa_rejects_resource_utilization_hpa(helm_runner) -> None:
    """Prevent HPA and VPA from controlling the same CPU signal."""

    with pytest.raises(HelmTemplateError, match="conflicts"):
        render_chart(
            helm_runner,
            CHART,
            values={
                "resources": {"requests": {"cpu": "100m"}},
                "autoscaling": {
                    "horizontal": {
                        "enabled": True,
                        "metrics": [
                            {
                                "type": "Resource",
                                "resource": {
                                    "name": "cpu",
                                    "target": {
                                        "type": "Utilization",
                                        "averageUtilization": 80,
                                    },
                                },
                            }
                        ],
                    },
                    "vertical": {
                        "enabled": True,
                        "updatePolicy": {
                            "updateMode": "Recreate",
                            "minReplicas": 2,
                        },
                        "resourcePolicy": {
                            "containerPolicies": [
                                {
                                    "containerName": "*",
                                    "controlledResources": ["cpu"],
                                    "controlledValues": "RequestsOnly",
                                    "maxAllowed": {"cpu": "2"},
                                }
                            ]
                        },
                    },
                },
            },
        )


@pytest.mark.parametrize(
    "metric",
    [
        pytest.param(
            {
                "type": "External",
                "external": {
                    "metric": {"name": "queue_depth"},
                    "target": {"type": "AverageValue", "averageValue": "20"},
                },
            },
            id="external",
        ),
        pytest.param(
            {
                "type": "Resource",
                "resource": {
                    "name": "cpu",
                    "target": {
                        "type": "AverageValue",
                        "averageValue": "200m",
                    },
                },
            },
            id="raw-resource-value",
        ),
    ],
)
def test_active_vpa_allows_compatible_hpa_metrics(
    helm_runner,
    metric: dict[str, Any],
) -> None:
    """Allow HPA signals that do not depend on VPA-managed request ratios."""

    manifests = render_manifests(
        helm_runner,
        values={
            "autoscaling": {
                "horizontal": {"enabled": True, "metrics": [metric]},
                "vertical": {
                    "enabled": True,
                    "updatePolicy": {
                        "updateMode": "Recreate",
                        "minReplicas": 2,
                    },
                    "resourcePolicy": {
                        "containerPolicies": [
                            {
                                "containerName": "*",
                                "controlledResources": ["cpu"],
                                "controlledValues": "RequestsOnly",
                                "maxAllowed": {"cpu": "2"},
                            }
                        ]
                    },
                },
            }
        },
    )

    kinds = {item["kind"] for item in manifests}
    assert {"HorizontalPodAutoscaler", "VerticalPodAutoscaler"} <= kinds
