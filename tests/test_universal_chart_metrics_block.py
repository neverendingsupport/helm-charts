"""Public metrics blocking tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import get_manifest, render_chart
from .conftest import HelmTemplateError
from .universal_chart_metrics_block_test_utils import (
    ingresses_by_name,
    nginx_ingress_values,
)
from .universal_chart_test_utils import CHART, render_manifests


def test_metrics_block_ingress_renders_for_nginx_ingress(
    helm_runner,
) -> None:
    """Block public metrics paths on every nginx Ingress host."""

    values = nginx_ingress_values(
        annotations={
            "nginx.ingress.kubernetes.io/permanent-redirect": (
                "https://example.com"
            ),
        }
    )
    values["ingress"]["hosts"].append(
        {
            "host": "alt.example.com",
            "paths": [{"path": "/", "pathType": "Prefix"}],
        }
    )
    values["ingress"]["tls"] = [
        {
            "secretName": "app-example-com",
            "hosts": ["app.example.com", "alt.example.com"],
        }
    ]
    ingresses = ingresses_by_name(render_manifests(helm_runner, values=values))
    main = ingresses[CHART.release]
    block = ingresses[f"{CHART.release}-metrics-block"]

    assert set(ingresses) == {CHART.release, f"{CHART.release}-metrics-block"}
    assert main["spec"]["rules"][0]["http"]["paths"][0]["path"] == "/"
    assert block["metadata"]["annotations"] == {
        "nginx.ingress.kubernetes.io/denylist-source-range": "0.0.0.0/0,::/0"
    }
    assert block["spec"]["ingressClassName"] == "nginx"
    assert block["spec"]["tls"][0]["secretName"] == "app-example-com"
    rules = block["spec"]["rules"]
    assert [rule["host"] for rule in rules] == [
        "app.example.com",
        "alt.example.com",
    ]
    assert all(rule["http"]["paths"][0]["path"] == "/metrics" for rule in rules)
    assert all(
        rule["http"]["paths"][0]["pathType"] == "Prefix" for rule in rules
    )


@pytest.mark.parametrize("path", ["/metrics/", "/metrics/debug"])
def test_metrics_block_ingress_rejects_duplicate_primary_path(
    helm_runner,
    path: str,
) -> None:
    """Reject primary paths that compete with the block Ingress."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values=nginx_ingress_values(
                paths=[
                    {"path": "/", "pathType": "Prefix"},
                    {"path": path, "pathType": "Prefix"},
                ]
            ),
        )


def test_metrics_block_ingress_uses_default_path_when_null(
    helm_runner,
) -> None:
    """Block /metrics when the ServiceMonitor omits its path."""

    values = nginx_ingress_values()
    values["serviceMonitor"]["path"] = None
    manifests = render_manifests(helm_runner, values=values)
    ingresses = ingresses_by_name(manifests)
    endpoint = get_manifest(manifests, "ServiceMonitor")["spec"]["endpoints"][0]
    block_path = ingresses[f"{CHART.release}-metrics-block"]["spec"]["rules"][
        0
    ]["http"]["paths"][0]

    assert "path" not in endpoint
    assert block_path["path"] == "/metrics"


def test_metrics_block_ingress_renders_without_class(helm_runner) -> None:
    """Support default ingress-nginx controllers with no named class."""

    ingresses = ingresses_by_name(
        render_manifests(
            helm_runner,
            values=nginx_ingress_values(class_name=None),
        )
    )
    block = ingresses[f"{CHART.release}-metrics-block"]

    assert "ingressClassName" not in block["spec"]


def test_metrics_block_ingress_handles_null_annotations(
    helm_runner,
) -> None:
    """Render when ingress annotations are explicitly null."""

    values = nginx_ingress_values()
    values["ingress"]["annotations"] = None
    ingresses = ingresses_by_name(render_manifests(helm_runner, values=values))

    assert f"{CHART.release}-metrics-block" in ingresses


def test_metrics_block_ingress_uses_public_path_override(
    helm_runner,
) -> None:
    """Block a public path that differs from the scrape path."""

    values = nginx_ingress_values(
        annotations={"kubernetes.io/ingress.class": "nginx"},
        class_name=None,
    )
    values["serviceMonitor"] = {
        "enabled": True,
        "path": "/internal/metrics",
        "blockExternalIngress": {"path": "/app/metrics"},
    }
    ingresses = ingresses_by_name(render_manifests(helm_runner, values=values))
    block = ingresses[f"{CHART.release}-metrics-block"]
    block_path = block["spec"]["rules"][0]["http"]["paths"][0]

    assert block["metadata"]["annotations"] == {
        "kubernetes.io/ingress.class": "nginx",
        "nginx.ingress.kubernetes.io/denylist-source-range": "0.0.0.0/0,::/0",
    }
    assert "ingressClassName" not in block["spec"]
    assert block_path["path"] == "/app/metrics"
    assert block_path["pathType"] == "Prefix"


def test_metrics_block_ingress_rejects_unsupported_class(
    helm_runner,
) -> None:
    """Reject classes where nginx deny rules cannot be enforced."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values=nginx_ingress_values(class_name="alb"),
        )


def test_metrics_block_ingress_allows_configured_nginx_class(
    helm_runner,
) -> None:
    """Allow alternate class names known to use ingress-nginx."""

    values = nginx_ingress_values(class_name="nginx-internal")
    values["serviceMonitor"]["blockExternalIngress"] = {
        "ingressClassNames": ["", "nginx", "nginx-internal"],
    }
    ingresses = ingresses_by_name(render_manifests(helm_runner, values=values))
    block = ingresses[f"{CHART.release}-metrics-block"]

    assert block["spec"]["ingressClassName"] == "nginx-internal"


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(
            {"serviceMonitor": {"enabled": True}},
            id="ingress-disabled",
        ),
        pytest.param(
            {
                **nginx_ingress_values(),
                "serviceMonitor": {"enabled": False},
            },
            id="service-monitor-disabled",
        ),
        pytest.param(
            {
                **nginx_ingress_values(),
                "serviceMonitor": {
                    "enabled": True,
                    "blockExternalIngress": {"enabled": False},
                },
            },
            id="block-disabled",
        ),
    ],
)
def test_metrics_block_ingress_is_conditional(
    helm_runner,
    values: dict[str, Any],
) -> None:
    """Render the block only when all required features are enabled."""

    ingresses = ingresses_by_name(render_manifests(helm_runner, values=values))

    assert f"{CHART.release}-metrics-block" not in ingresses


@pytest.mark.parametrize(
    "block_values",
    [
        pytest.param({"enabled": "hero"}, id="enabled-is-not-boolean"),
        pytest.param(
            {"denylistSourceRange": "not-a-cidr"},
            id="denylist-is-not-cidr",
        ),
    ],
)
def test_metrics_block_rejects_invalid_values(
    helm_runner,
    block_values: dict[str, Any],
) -> None:
    """Reject malformed public metrics block values."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "serviceMonitor": {
                    "enabled": True,
                    "blockExternalIngress": block_values,
                }
            },
        )
