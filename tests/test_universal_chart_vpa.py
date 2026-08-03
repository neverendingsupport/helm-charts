"""VerticalPodAutoscaler tests for universal-chart autosizing."""

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


def _active_autosizing(mode: str = "Recreate") -> dict[str, Any]:
    """Build bounded active autosizing values."""

    return {
        "enabled": True,
        "updatePolicy": {"updateMode": mode, "minReplicas": 2},
        "resourcePolicy": {
            "containerPolicies": [
                {
                    "containerName": "*",
                    "mode": "Auto",
                    "controlledResources": ["cpu", "memory"],
                    "controlledValues": "RequestsOnly",
                    "minAllowed": {"cpu": "50m", "memory": "64Mi"},
                    "maxAllowed": {"cpu": "2", "memory": "2Gi"},
                }
            ]
        },
    }


def test_vpa_is_absent_by_default(helm_runner) -> None:
    """Do not require VPA CRDs for workloads that have not opted in."""

    manifests = render_manifests(helm_runner)

    assert all(item["kind"] != "VerticalPodAutoscaler" for item in manifests)


def test_vpa_off_renders_recommendation_policy(helm_runner) -> None:
    """Create a recommendation-only VPA under autosizing."""

    vpa = render_manifest(
        helm_runner,
        "VerticalPodAutoscaler",
        values={
            "autosizing": {
                "enabled": True,
                "annotations": {"argocd.argoproj.io/sync-wave": "10"},
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


def test_autosizing_keeps_fixed_deployment_replicas(helm_runner) -> None:
    """Keep replica ownership on the Deployment while VPA is enabled."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={
            "replicaCount": 3,
            "autosizing": {"enabled": True},
        },
    )

    assert deployment["spec"]["replicas"] == 3


@pytest.mark.parametrize("mode", ["Initial", "Recreate", "InPlaceOrRecreate"])
def test_vpa_active_modes_render_with_explicit_ceilings(
    helm_runner,
    mode: str,
) -> None:
    """Render every supported mutating mode when ceilings are set."""

    autosizing = _active_autosizing(mode)
    autosizing["updatePolicy"]["minReplicas"] = 3
    vpa = render_manifest(
        helm_runner,
        "VerticalPodAutoscaler",
        values={"autosizing": autosizing},
    )

    assert vpa["spec"]["updatePolicy"] == {
        "updateMode": mode,
        "minReplicas": 3,
    }
    assert vpa["spec"]["resourcePolicy"] == autosizing["resourcePolicy"]


def test_vpa_supports_explicit_per_container_limit_control(helm_runner) -> None:
    """Pass per-container RequestsAndLimits policies through unchanged."""

    autosizing = _active_autosizing("Initial")
    policy = autosizing["resourcePolicy"]["containerPolicies"][0]
    policy["containerName"] = "universal-chart"
    policy["controlledValues"] = "RequestsAndLimits"

    vpa = render_manifest(
        helm_runner,
        "VerticalPodAutoscaler",
        values={"autosizing": autosizing},
    )

    assert vpa["spec"]["resourcePolicy"]["containerPolicies"] == [policy]


def test_vpa_accepts_kubernetes_exa_quantity_suffix(helm_runner) -> None:
    """Accept the full Kubernetes decimal-SI quantity suffix set."""

    autosizing = _active_autosizing("Initial")
    autosizing["resourcePolicy"]["containerPolicies"][0]["maxAllowed"][
        "cpu"
    ] = "1E"

    vpa = render_manifest(
        helm_runner,
        "VerticalPodAutoscaler",
        values={"autosizing": autosizing},
    )

    assert (
        vpa["spec"]["resourcePolicy"]["containerPolicies"][0]["maxAllowed"][
            "cpu"
        ]
        == "1E"
    )


@pytest.mark.parametrize(
    ("autosizing", "message"),
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
    autosizing: dict[str, Any],
    message: str,
) -> None:
    """Reject active policies without ownership and safety bounds."""

    with pytest.raises(HelmTemplateError, match=message):
        render_chart(
            helm_runner,
            CHART,
            values={"autosizing": autosizing},
        )


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(
            {
                "autosizing": {
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
            },
            id="malformed-resource-quantity",
        ),
        pytest.param(
            {
                "autosizing": {
                    "enabled": True,
                    "resourcePolicy": {
                        "containerPolicies": [
                            {
                                "containerName": "*",
                                "controlledResources": ["cpu"],
                                "controlledValues": "RequestsOnly",
                                "maxAllowed": {"cpu": "1K"},
                            }
                        ]
                    },
                }
            },
            id="unsupported-uppercase-kilo-quantity",
        ),
        pytest.param(
            {"autosizing": {"annotations": {"example.com/order": 10}}},
            id="annotation-is-not-string",
        ),
        pytest.param(
            {"autoscaling": {"vertical": {"enabled": True}}},
            id="unreleased-vertical-interface-is-rejected",
        ),
    ],
)
def test_vpa_schema_rejects_invalid_values(
    helm_runner,
    values: dict[str, Any],
) -> None:
    """Reject malformed or obsolete autosizing values."""

    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values=values)


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
                "autosizing": {
                    "enabled": True,
                    "updatePolicy": {
                        "updateMode": mode,
                        "minReplicas": 2,
                    },
                }
            },
        )


@pytest.mark.parametrize(
    "mode", ["Off", "Initial", "Recreate", "InPlaceOrRecreate"]
)
def test_autoscaling_and_autosizing_are_mutually_exclusive(
    helm_runner,
    mode: str,
) -> None:
    """Reject competing HPA and VPA resources in every VPA mode."""

    autosizing = (
        {"enabled": True} if mode == "Off" else _active_autosizing(mode)
    )
    with pytest.raises(HelmTemplateError, match="mutually exclusive"):
        render_chart(
            helm_runner,
            CHART,
            values={
                "autoscaling": {"enabled": True},
                "autosizing": autosizing,
            },
        )
