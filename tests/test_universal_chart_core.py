"""Core deployment and service tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import get_manifest, get_primary_container, render_chart
from .universal_chart_test_utils import CHART, render_manifests


def test_universal_chart_renders_with_required_values(helm_runner) -> None:
    """Render the chart with only its required values."""

    rendered = render_chart(helm_runner, CHART)

    assert "kind: Deployment" in rendered
    assert "ghcr.io/example/app:1.2.3" in rendered


def test_name_override_updates_all_references(helm_runner) -> None:
    """Apply the name override to every chart-managed reference."""

    override = "custom-app"
    manifests = render_manifests(
        helm_runner,
        values={"nameOverride": override},
    )
    short_name = override
    full_name = f"{CHART.release}-{override}"

    deployment = get_manifest(manifests, "Deployment")
    service = get_manifest(manifests, "Service")
    service_account = get_manifest(manifests, "ServiceAccount")

    label_targets = [
        deployment["metadata"]["labels"],
        deployment["spec"]["selector"]["matchLabels"],
        deployment["spec"]["template"]["metadata"]["labels"],
        service["metadata"]["labels"],
        service["spec"]["selector"],
        service_account["metadata"]["labels"],
    ]
    for labels in label_targets:
        assert labels["app.kubernetes.io/name"] == short_name

    assert deployment["metadata"]["name"] == full_name
    assert service["metadata"]["name"] == full_name
    assert service_account["metadata"]["name"] == full_name
    assert (
        deployment["spec"]["template"]["spec"]["serviceAccountName"]
        == full_name
    )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        pytest.param(
            {
                "resources.requests.cpu": "250m",
                "resources.requests.memory": "512Mi",
            },
            {"requests": {"cpu": "250m", "memory": "512Mi"}},
            id="requests",
        ),
        pytest.param(
            {"resources.limits.memory": "1024Mi"},
            {"limits": {"memory": "1024Mi"}},
            id="limits",
        ),
        pytest.param(
            {
                "resources.requests.cpu": "250m",
                "resources.requests.memory": "512Mi",
                "resources.limits.memory": "1024Mi",
            },
            {
                "requests": {"cpu": "250m", "memory": "512Mi"},
                "limits": {"memory": "1024Mi"},
            },
            id="limits-and-requests",
        ),
    ],
)
def test_resources_render_requested_limits(
    helm_runner,
    values: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """Render each supported resource combination."""

    container = get_primary_container(
        render_manifests(helm_runner, values=values)
    )

    assert container["resources"] == expected


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        pytest.param(
            "SOME_VALUE",
            "hello world",
            {"name": "SOME_VALUE", "value": "hello world"},
            id="string",
        ),
        pytest.param(
            "POD_NAME",
            {"valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}}},
            {
                "name": "POD_NAME",
                "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
            },
            id="field-ref",
        ),
        pytest.param(
            "SECRET_THING",
            {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "my-secret",
                        "key": "password",
                    }
                }
            },
            {
                "name": "SECRET_THING",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "my-secret",
                        "key": "password",
                    }
                },
            },
            id="secret-key-ref",
        ),
    ],
)
def test_extra_env_vars_accept_supported_values(
    helm_runner,
    name: str,
    value: Any,
    expected: dict[str, Any],
) -> None:
    """Render strings and Kubernetes valueFrom entries."""

    manifests = render_manifests(
        helm_runner,
        values={"extraEnvVars": {name: value}},
    )
    container = get_primary_container(manifests)
    env = {entry["name"]: entry for entry in container["env"]}

    assert env[name] == expected


def test_deployment_annotations_render_correctly(helm_runner) -> None:
    """Add requested annotations to Deployment metadata."""

    deployment = get_manifest(
        render_manifests(
            helm_runner,
            values={
                "deployment": {
                    "annotations": {"reloader.stakater.com/auto": "true"}
                }
            },
        ),
        "Deployment",
    )

    assert deployment["metadata"]["annotations"] == {
        "reloader.stakater.com/auto": "true"
    }


def test_service_metadata_only_updates_primary_service(helm_runner) -> None:
    """Keep application metadata off the chart's metrics service."""

    manifests = render_manifests(
        helm_runner,
        values={
            "service": {
                "annotations": {
                    "teleport.dev/name": "example-app",
                    "teleport.dev/public-addr": (
                        "example-app.teleport.apps.herodevs.io"
                    ),
                },
                "labels": {"herodevs.com/teleport-access": "true"},
            },
            "serviceMonitor": {"alternatePort": 9090},
        },
    )
    services = [
        manifest for manifest in manifests if manifest.get("kind") == "Service"
    ]
    main_service = next(
        service
        for service in services
        if service["metadata"]["name"] == CHART.release
    )
    metrics_service = next(
        service
        for service in services
        if service["metadata"]["name"] == f"{CHART.release}-metrics"
    )

    assert main_service["metadata"]["annotations"] == {
        "teleport.dev/name": "example-app",
        "teleport.dev/public-addr": "example-app.teleport.apps.herodevs.io",
    }
    assert (
        main_service["metadata"]["labels"]["herodevs.com/teleport-access"]
        == "true"
    )
    assert "annotations" not in metrics_service["metadata"]
    assert (
        "herodevs.com/teleport-access"
        not in metrics_service["metadata"]["labels"]
    )
