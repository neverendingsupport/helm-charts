"""Shared values and manifest helpers for metrics-block tests."""

from __future__ import annotations

from typing import Any

from .chart_test_utils import manifests_by_name


def ingresses_by_name(
    manifests: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return ingress manifests keyed by name."""

    return manifests_by_name(manifests, "Ingress")


def nginx_ingress_values(
    *,
    paths: list[dict[str, str]] | None = None,
    annotations: dict[str, str] | None = None,
    class_name: str | None = "nginx",
) -> dict[str, Any]:
    """Build nginx Ingress values with metrics scraping enabled."""

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


def regex_ingress_values(
    *,
    block_external_ingress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build nginx regex/rewrite Ingress values with metrics enabled."""

    values = nginx_ingress_values(
        paths=[
            {
                "path": "/(eol)(/|$)(.*)",
                "pathType": "ImplementationSpecific",
            }
        ],
        annotations={
            "nginx.ingress.kubernetes.io/rewrite-target": "/$1/$3",
            "nginx.ingress.kubernetes.io/use-regex": "true",
        },
    )
    values["serviceMonitor"]["path"] = "/eol/api/metrics"
    if block_external_ingress is not None:
        values["serviceMonitor"][
            "blockExternalIngress"
        ] = block_external_ingress

    return values
