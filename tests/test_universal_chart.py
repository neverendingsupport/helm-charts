"""Unit tests for the universal chart."""

from __future__ import annotations

import pytest

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    get_primary_container,
    load_manifests,
    render_chart,
)
from .conftest import HelmTemplateError

CHART = ChartContext("universal-chart")


def test_universal_chart_renders_with_required_values(helm_runner) -> None:
    """Ensure the chart renders when only the required values are set."""

    rendered = render_chart(helm_runner, CHART)
    assert "kind: Deployment" in rendered
    assert "ghcr.io/example/app:1.2.3" in rendered


def test_name_override_updates_all_references(helm_runner) -> None:
    """Ensure every manifest reflects the requested name override."""

    override = "custom-app"
    rendered = render_chart(
        helm_runner,
        CHART,
        values={"nameOverride": override},
    )
    manifests = load_manifests(rendered)
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


def test_resources_include_requests_for_cpu_and_memory(helm_runner) -> None:
    """Ensure CPU and memory requests are rendered when specified."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "resources.requests.cpu": "250m",
            "resources.requests.memory": "512Mi",
        },
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    assert container["resources"] == {
        "requests": {"cpu": "250m", "memory": "512Mi"}
    }


def test_resources_include_memory_limits(helm_runner) -> None:
    """Ensure memory limits are rendered when specified."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"resources.limits.memory": "1024Mi"},
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    assert container["resources"] == {"limits": {"memory": "1024Mi"}}


def test_resources_include_limits_and_requests(helm_runner) -> None:
    """Ensure limits and requests coexist when both are defined."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "resources.requests.cpu": "250m",
            "resources.requests.memory": "512Mi",
            "resources.limits.memory": "1024Mi",
        },
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    assert container["resources"] == {
        "requests": {"cpu": "250m", "memory": "512Mi"},
        "limits": {"memory": "1024Mi"},
    }


def test_extra_env_vars_accept_string_values(helm_runner) -> None:
    """Ensure extraEnvVars renders simple string values."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"extraEnvVars": {"SOME_VALUE": "hello world"}},
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    env = {entry["name"]: entry for entry in container["env"]}

    assert env["SOME_VALUE"] == {"name": "SOME_VALUE", "value": "hello world"}


def test_extra_env_vars_accept_field_ref_objects(helm_runner) -> None:
    """Ensure extraEnvVars renders valueFrom fieldRef entries."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "extraEnvVars": {
                "POD_NAME": {
                    "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
                }
            }
        },
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    env = {entry["name"]: entry for entry in container["env"]}

    assert env["POD_NAME"] == {
        "name": "POD_NAME",
        "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
    }


def test_extra_env_vars_accept_secret_key_refs(helm_runner) -> None:
    """Ensure extraEnvVars renders valueFrom secretKeyRef entries."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "extraEnvVars": {
                "SECRET_THING": {
                    "valueFrom": {
                        "secretKeyRef": {"name": "my-secret", "key": "password"}
                    }
                }
            }
        },
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    env = {entry["name"]: entry for entry in container["env"]}

    assert env["SECRET_THING"] == {
        "name": "SECRET_THING",
        "valueFrom": {"secretKeyRef": {"name": "my-secret", "key": "password"}},
    }


def test_deployment_annotations_renders_correctly(helm_runner) -> None:
    """Ensure deployment annotations are rendered."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "deployment": {
                "annotations": {"reloader.stakater.com/auto": "true"}
            }
        },
    )
    manifests = load_manifests(rendered)
    deployment = get_manifest(manifests, "Deployment")
    metadata = deployment["metadata"]

    assert "annotations" in metadata
    assert metadata["annotations"].get("reloader.stakater.com/auto") == "true"


def test_service_monitor_renders_when_enabled(helm_runner) -> None:
    """Ensure a ServiceMonitor is created when enabled."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"serviceMonitor": {"enabled": True}},
    )
    manifests = load_manifests(rendered)
    service = get_manifest(manifests, "Service")
    service_monitor = get_manifest(manifests, "ServiceMonitor")

    selector_labels = service_monitor["spec"]["selector"]["matchLabels"]
    assert selector_labels == service["spec"]["selector"]

    endpoint = service_monitor["spec"]["endpoints"][0]
    assert endpoint["port"] == "http"
    assert endpoint["path"] == "/metrics"
    assert "interval" not in endpoint


def test_service_monitor_is_not_rendered_when_disabled(helm_runner) -> None:
    """Ensure the ServiceMonitor is omitted when disabled."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"serviceMonitor": {"enabled": False}},
    )
    manifests = load_manifests(rendered)

    assert all(
        manifest.get("kind") != "ServiceMonitor" for manifest in manifests
    )


def test_service_monitor_supports_custom_path_and_interval(helm_runner) -> None:
    """Ensure path and interval overrides render in the ServiceMonitor."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "serviceMonitor": {
                "enabled": True,
                "path": "/app/metrics",
                "interval": 30,
            }
        },
    )
    manifests = load_manifests(rendered)
    endpoint = get_manifest(manifests, "ServiceMonitor")["spec"]["endpoints"][0]

    assert endpoint["path"] == "/app/metrics"
    assert endpoint["interval"] == "30s"


def test_service_monitor_interval_supports_minimum_value(helm_runner) -> None:
    """Ensure the minimum interval value renders correctly."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"serviceMonitor": {"enabled": True, "interval": 1}},
    )
    manifests = load_manifests(rendered)
    endpoint = get_manifest(manifests, "ServiceMonitor")["spec"]["endpoints"][0]

    assert endpoint["interval"] == "1s"


def test_service_monitor_path_may_be_null(helm_runner) -> None:
    """Ensure the path field is omitted when explicitly set to null."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"serviceMonitor": {"enabled": True, "path": None}},
    )
    manifests = load_manifests(rendered)
    endpoint = get_manifest(manifests, "ServiceMonitor")["spec"]["endpoints"][0]

    assert "path" not in endpoint


def test_service_monitor_rejects_invalid_enabled_value(helm_runner) -> None:
    """Reject non-boolean values for the service monitor toggle."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"serviceMonitor": {"enabled": "hero"}},
        )


def test_service_monitor_interval_rejects_negative_values(helm_runner) -> None:
    """Ensure the schema rejects negative interval values."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"serviceMonitor": {"enabled": True, "interval": -5}},
        )


def test_service_monitor_interval_rejects_zero(helm_runner) -> None:
    """Ensure the schema rejects interval values below the minimum."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"serviceMonitor": {"enabled": True, "interval": 0}},
        )


def test_spread_azs_appends_topology_constraint(helm_runner) -> None:
    """Ensure enabling AZ spread adds the extra topology constraint."""

    rendered = render_chart(helm_runner, CHART, values={"spread_azs": True})
    manifests = load_manifests(rendered)
    deployment = get_manifest(manifests, "Deployment")
    constraints = deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints", []
    )

    assert any(
        constraint.get("topologyKey") == "karpenter.sh/zone"
        for constraint in constraints
    )


def test_spread_spot_appends_topology_constraint(helm_runner) -> None:
    """Ensure enabling spot spread adds the extra topology constraint."""

    rendered = render_chart(helm_runner, CHART, values={"spread_spot": True})
    manifests = load_manifests(rendered)
    deployment = get_manifest(manifests, "Deployment")
    constraints = deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints", []
    )

    assert any(
        constraint.get("topologyKey") == "karpenter.sh/capacity-type"
        for constraint in constraints
    )


def test_spread_topology_defaults_do_not_include_extra_spreads(helm_runner) -> None:
    """Ensure spread toggles default to only the configured constraints."""

    rendered = render_chart(helm_runner, CHART)
    manifests = load_manifests(rendered)
    deployment = get_manifest(manifests, "Deployment")
    constraints = deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints", []
    )

    assert all(
        constraint.get("topologyKey")
        not in {"karpenter.sh/zone", "karpenter.sh/capacity-type"}
        for constraint in constraints
    )


def test_spread_values_reject_invalid_booleans(helm_runner) -> None:
    """Invalid boolean values fail schema validation for spread options."""

    for key in ("spread_azs", "spread_spot"):
        with pytest.raises(HelmTemplateError):
            render_chart(helm_runner, CHART, values={key: "hero"})

