"""ServiceMonitor and metrics Service tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import get_manifest, manifests_by_name, render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import (
    CHART,
    render_manifest,
    render_manifests,
)


def test_service_monitor_renders_when_enabled(helm_runner) -> None:
    """Match the workload Service and expose its HTTP endpoint."""

    manifests = render_manifests(
        helm_runner,
        values={"serviceMonitor": {"enabled": True}},
    )
    service = get_manifest(manifests, "Service")
    service_monitor = get_manifest(manifests, "ServiceMonitor")

    assert service_monitor["spec"]["selector"]["matchLabels"] == (
        service["spec"]["selector"]
    )
    endpoint = service_monitor["spec"]["endpoints"][0]
    assert endpoint["port"] == "http"
    assert endpoint["path"] == "/metrics"
    assert "interval" not in endpoint


def test_service_monitor_is_not_rendered_when_disabled(helm_runner) -> None:
    """Omit the ServiceMonitor when disabled."""

    manifests = render_manifests(
        helm_runner,
        values={"serviceMonitor": {"enabled": False}},
    )

    assert all(item.get("kind") != "ServiceMonitor" for item in manifests)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        pytest.param(
            {"path": "/app/metrics", "interval": 30},
            {"port": "http", "path": "/app/metrics", "interval": "30s"},
            id="custom-path-and-interval",
        ),
        pytest.param(
            {"interval": 1},
            {"port": "http", "path": "/metrics", "interval": "1s"},
            id="minimum-interval",
        ),
        pytest.param(
            {"path": None},
            {"port": "http"},
            id="null-path",
        ),
    ],
)
def test_service_monitor_endpoint_overrides(
    helm_runner,
    values: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """Render supported endpoint overrides."""

    values["enabled"] = True
    service_monitor = render_manifest(
        helm_runner,
        "ServiceMonitor",
        values={"serviceMonitor": values},
    )

    assert service_monitor["spec"]["endpoints"][0] == expected


def test_metrics_service_renders_when_alternate_port_is_set(
    helm_runner,
) -> None:
    """Create a dedicated Service for an alternate metrics port."""

    manifests = render_manifests(
        helm_runner,
        values={"serviceMonitor": {"alternatePort": 9090}},
    )
    services = manifests_by_name(manifests, "Service")
    main = services[CHART.release]
    metrics = services[f"{CHART.release}-metrics"]

    assert len(services) == 2
    assert metrics["spec"]["type"] == "ClusterIP"
    assert metrics["spec"]["selector"] == main["spec"]["selector"]
    assert metrics["spec"]["ports"] == [
        {
            "name": "metrics",
            "port": 9090,
            "protocol": "TCP",
            "targetPort": 9090,
        }
    ]


def test_service_monitor_uses_alternate_metrics_service(helm_runner) -> None:
    """Target the dedicated Service when an alternate port is set."""

    service_monitor = render_manifest(
        helm_runner,
        "ServiceMonitor",
        values={
            "serviceMonitor": {
                "enabled": True,
                "alternatePort": 9090,
            }
        },
    )

    endpoint = service_monitor["spec"]["endpoints"][0]
    assert endpoint["port"] == "metrics"
    assert endpoint["path"] == "/metrics"


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({"enabled": "hero"}, id="enabled-is-not-boolean"),
        pytest.param(
            {"enabled": True, "path": "metrics"},
            id="path-is-not-absolute",
        ),
        pytest.param(
            {"enabled": True, "interval": -5},
            id="negative-interval",
        ),
        pytest.param(
            {"enabled": True, "interval": 0},
            id="zero-interval",
        ),
    ],
)
def test_service_monitor_schema_rejects_invalid_values(
    helm_runner,
    values: dict[str, Any],
) -> None:
    """Reject malformed ServiceMonitor values."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"serviceMonitor": values},
        )
