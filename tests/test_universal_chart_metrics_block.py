"""Tests for universal-chart public metrics blocking."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    load_manifests,
    render_chart,
)
from .conftest import HelmTemplateError

CHART = ChartContext("universal-chart")


def _ingresses_by_name(
    manifests: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return ingress manifests keyed by name."""

    return {
        manifest["metadata"]["name"]: manifest
        for manifest in manifests
        if manifest.get("kind") == "Ingress"
    }


def _nginx_ingress_values(
    *,
    paths: list[dict[str, str]] | None = None,
    annotations: dict[str, str] | None = None,
    class_name: str | None = "nginx",
) -> dict[str, Any]:
    """Return values for an nginx ingress with metrics scraping enabled."""

    ingress: dict[str, Any] = {
        "enabled": True,
        "hosts": [
            {
                "host": "app.example.com",
                "paths": paths or [{"path": "/", "pathType": "Prefix"}],
            }
        ],
    }
    if class_name is not None:
        ingress["className"] = class_name
    if annotations is not None:
        ingress["annotations"] = annotations

    return {
        "ingress": ingress,
        "serviceMonitor": {"enabled": True, "path": "/metrics"},
    }


def test_metrics_block_ingress_renders_for_nginx_ingress(
    helm_runner,
) -> None:
    """Ensure nginx ingress blocks public access to ServiceMonitor metrics."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "ingress": {
                "enabled": True,
                "className": "nginx",
                "annotations": {
                    "nginx.ingress.kubernetes.io/permanent-redirect": (
                        "https://example.com"
                    ),
                },
                "hosts": [
                    {
                        "host": "app.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    },
                    {
                        "host": "alt.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    },
                ],
                "tls": [
                    {
                        "secretName": "app-example-com",
                        "hosts": ["app.example.com", "alt.example.com"],
                    }
                ],
            },
            "serviceMonitor": {"enabled": True, "path": "/metrics"},
        },
    )
    manifests = load_manifests(rendered)
    ingresses = _ingresses_by_name(manifests)
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
    """Reject primary paths that would compete with the block Ingress."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values=_nginx_ingress_values(
                paths=[
                    {"path": "/", "pathType": "Prefix"},
                    {"path": path, "pathType": "Prefix"},
                ]
            ),
        )


def test_metrics_block_ingress_uses_prometheus_default_path_when_null(
    helm_runner,
) -> None:
    """Block /metrics when ServiceMonitor omits path."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "ingress": {
                "enabled": True,
                "className": "nginx",
                "hosts": [
                    {
                        "host": "app.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    }
                ],
            },
            "serviceMonitor": {"enabled": True, "path": None},
        },
    )
    manifests = load_manifests(rendered)
    ingresses = _ingresses_by_name(manifests)
    endpoint = get_manifest(manifests, "ServiceMonitor")["spec"]["endpoints"][0]
    block_path = ingresses[f"{CHART.release}-metrics-block"]["spec"]["rules"][
        0
    ]["http"]["paths"][0]

    assert "path" not in endpoint
    assert block_path["path"] == "/metrics"


def test_metrics_block_ingress_renders_for_classless_ingress(
    helm_runner,
) -> None:
    """Mirror classless ingresses for default ingress-nginx controllers."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "ingress": {
                "enabled": True,
                "hosts": [
                    {
                        "host": "app.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    }
                ],
            },
            "serviceMonitor": {"enabled": True},
        },
    )
    manifests = load_manifests(rendered)
    ingresses = _ingresses_by_name(manifests)
    block = ingresses[f"{CHART.release}-metrics-block"]

    assert "ingressClassName" not in block["spec"]


def test_metrics_block_ingress_handles_null_annotations(
    helm_runner,
) -> None:
    """Avoid failing when callers explicitly set ingress.annotations to null."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "ingress": {
                "enabled": True,
                "className": "nginx",
                "annotations": None,
                "hosts": [
                    {
                        "host": "app.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    }
                ],
            },
            "serviceMonitor": {"enabled": True},
        },
    )
    manifests = load_manifests(rendered)
    ingresses = _ingresses_by_name(manifests)

    assert f"{CHART.release}-metrics-block" in ingresses


def test_metrics_block_ingress_uses_public_path_override(
    helm_runner,
) -> None:
    """Allow apps to block a public path that differs from the scrape path."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "ingress": {
                "enabled": True,
                "annotations": {"kubernetes.io/ingress.class": "nginx"},
                "hosts": [
                    {
                        "host": "app.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    }
                ],
            },
            "serviceMonitor": {
                "enabled": True,
                "path": "/internal/metrics",
                "blockExternalIngress": {"path": "/app/metrics"},
            },
        },
    )
    manifests = load_manifests(rendered)
    ingresses = _ingresses_by_name(manifests)
    block = ingresses[f"{CHART.release}-metrics-block"]
    block_path = ingresses[f"{CHART.release}-metrics-block"]["spec"]["rules"][
        0
    ]["http"]["paths"][0]

    assert block["metadata"]["annotations"] == {
        "kubernetes.io/ingress.class": "nginx",
        "nginx.ingress.kubernetes.io/denylist-source-range": "0.0.0.0/0,::/0",
    }
    assert "ingressClassName" not in block["spec"]
    assert block_path["path"] == "/app/metrics"
    assert block_path["pathType"] == "Prefix"


def test_metrics_block_ingress_rejects_rewrite_ingress(
    helm_runner,
) -> None:
    """Reject ingress rules where nginx path precedence cannot be guaranteed."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "ingress": {
                    "enabled": True,
                    "className": "nginx",
                    "annotations": {
                        "nginx.ingress.kubernetes.io/rewrite-target": "/$3",
                    },
                    "hosts": [
                        {
                            "host": "app.example.com",
                            "paths": [
                                {
                                    "path": "/(app)(/|$)(.*)",
                                    "pathType": "ImplementationSpecific",
                                }
                            ],
                        }
                    ],
                },
                "serviceMonitor": {
                    "enabled": True,
                    "path": "/metrics",
                    "blockExternalIngress": {"path": "/app/metrics"},
                },
            },
        )


def test_metrics_block_ingress_rejects_case_variant_regex_ingress(
    helm_runner,
) -> None:
    """Reject nginx truthy use-regex values beyond lowercase true."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "ingress": {
                    "enabled": True,
                    "className": "nginx",
                    "annotations": {
                        "nginx.ingress.kubernetes.io/use-regex": "True",
                    },
                    "hosts": [
                        {
                            "host": "app.example.com",
                            "paths": [
                                {
                                    "path": "/(app)(/|$)(.*)",
                                    "pathType": "ImplementationSpecific",
                                }
                            ],
                        }
                    ],
                },
                "serviceMonitor": {"enabled": True},
            },
        )


def test_metrics_block_ingress_rejects_unsupported_ingress_class(
    helm_runner,
) -> None:
    """Reject classes where the nginx deny rule cannot be safely enforced."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "ingress": {
                    "enabled": True,
                    "className": "alb",
                    "hosts": [
                        {
                            "host": "app.example.com",
                            "paths": [{"path": "/", "pathType": "Prefix"}],
                        }
                    ],
                },
                "serviceMonitor": {"enabled": True},
            },
        )


def test_metrics_block_ingress_allows_configured_nginx_class(
    helm_runner,
) -> None:
    """Allow alternate class names when they are known to use ingress-nginx."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "ingress": {
                "enabled": True,
                "className": "nginx-internal",
                "hosts": [
                    {
                        "host": "app.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    }
                ],
            },
            "serviceMonitor": {
                "enabled": True,
                "blockExternalIngress": {
                    "ingressClassNames": ["", "nginx", "nginx-internal"],
                },
            },
        },
    )
    manifests = load_manifests(rendered)
    ingresses = _ingresses_by_name(manifests)
    block = ingresses[f"{CHART.release}-metrics-block"]

    assert block["spec"]["ingressClassName"] == "nginx-internal"


@pytest.mark.parametrize(
    "values",
    [
        {"serviceMonitor": {"enabled": True}},
        {
            "ingress": {
                "enabled": True,
                "className": "nginx",
                "hosts": [
                    {
                        "host": "app.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    }
                ],
            },
            "serviceMonitor": {"enabled": False},
        },
        {
            "ingress": {
                "enabled": True,
                "className": "nginx",
                "hosts": [
                    {
                        "host": "app.example.com",
                        "paths": [{"path": "/", "pathType": "Prefix"}],
                    }
                ],
            },
            "serviceMonitor": {
                "enabled": True,
                "blockExternalIngress": {"enabled": False},
            },
        },
    ],
)
def test_metrics_block_ingress_is_conditional(
    helm_runner,
    values: dict[str, Any],
) -> None:
    """Ensure the public metrics block only renders when it can be enforced."""

    rendered = render_chart(helm_runner, CHART, values=values)
    manifests = load_manifests(rendered)
    ingresses = _ingresses_by_name(manifests)

    assert f"{CHART.release}-metrics-block" not in ingresses


def test_metrics_block_rejects_invalid_enabled_value(helm_runner) -> None:
    """Reject non-boolean values for the public metrics block toggle."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "serviceMonitor": {
                    "enabled": True,
                    "blockExternalIngress": {"enabled": "hero"},
                }
            },
        )


def test_metrics_block_rejects_invalid_denylist_source_range(
    helm_runner,
) -> None:
    """Reject denylist values that are not CIDR-shaped."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "serviceMonitor": {
                    "enabled": True,
                    "blockExternalIngress": {
                        "denylistSourceRange": "not-a-cidr",
                    },
                }
            },
        )
