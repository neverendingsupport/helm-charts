"""Unit tests for the universal chart."""
from __future__ import annotations

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    get_primary_container,
    load_manifests,
    render_chart,
)

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
