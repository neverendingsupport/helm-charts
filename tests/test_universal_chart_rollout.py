"""Deployment rollout and container lifecycle tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import get_primary_container, render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifest, render_manifests


def test_rollout_controls_are_omitted_by_default(helm_runner) -> None:
    """Preserve Kubernetes defaults when rollout values are unset."""

    deployment = render_manifest(helm_runner, "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]

    assert "strategy" not in deployment["spec"]
    assert "minReadySeconds" not in deployment["spec"]
    assert "progressDeadlineSeconds" not in deployment["spec"]
    assert "lifecycle" not in container


def test_rolling_update_strategy_and_timing_render(helm_runner) -> None:
    """Render custom rolling parameters and rollout timing together."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={
            "deployment": {
                "strategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {
                        "maxSurge": "25%",
                        "maxUnavailable": 0,
                    },
                },
                "minReadySeconds": 15,
                "progressDeadlineSeconds": 300,
            }
        },
    )

    assert deployment["spec"]["strategy"] == {
        "type": "RollingUpdate",
        "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": 0},
    }
    assert deployment["spec"]["minReadySeconds"] == 15
    assert deployment["spec"]["progressDeadlineSeconds"] == 300


def test_rolling_update_allows_zero_padded_nonzero_percentage(
    helm_runner,
) -> None:
    """Treat a zero-padded percentage according to its numeric value."""

    strategy = {
        "type": "RollingUpdate",
        "rollingUpdate": {"maxSurge": "01%", "maxUnavailable": 0},
    }
    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={"deployment": {"strategy": strategy}},
    )

    assert deployment["spec"]["strategy"] == strategy


def test_recreate_strategy_omits_rolling_update_fields(helm_runner) -> None:
    """Render Recreate without a conflicting rollingUpdate block."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={"deployment": {"strategy": {"type": "Recreate"}}},
    )

    assert deployment["spec"]["strategy"] == {"type": "Recreate"}


def test_min_ready_uses_kubernetes_default_progress_deadline(
    helm_runner,
) -> None:
    """Accept a readiness window below the default 600-second deadline."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={"deployment": {"minReadySeconds": 599}},
    )

    assert deployment["spec"]["minReadySeconds"] == 599
    assert "progressDeadlineSeconds" not in deployment["spec"]


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(
            {"exec": {"command": ["/bin/sh", "-c", "sleep 10"]}},
            id="exec",
        ),
        pytest.param(
            {
                "httpGet": {
                    "path": "/drain",
                    "port": "http",
                    "scheme": "HTTP",
                    "httpHeaders": [{"name": "X-Drain", "value": "true"}],
                }
            },
            id="http-get",
        ),
        pytest.param({"sleep": {"seconds": 10}}, id="sleep"),
    ],
)
def test_main_container_lifecycle_handlers_render(
    helm_runner,
    handler: dict[str, Any],
) -> None:
    """Render each supported lifecycle handler for the main container."""

    manifests = render_manifests(
        helm_runner,
        values={"lifecycle": {"preStop": handler}},
    )

    assert get_primary_container(manifests)["lifecycle"] == {"preStop": handler}


def test_post_start_lifecycle_hook_renders(helm_runner) -> None:
    """Support the second Kubernetes container lifecycle phase."""

    handler = {"exec": {"command": ["/app/warm-cache"]}}
    manifests = render_manifests(
        helm_runner,
        values={"lifecycle": {"postStart": handler}},
    )

    assert get_primary_container(manifests)["lifecycle"] == {
        "postStart": handler
    }


def test_exec_lifecycle_allows_empty_arguments(helm_runner) -> None:
    """Allow empty positional arguments in a nonempty exec command."""

    handler = {"exec": {"command": ["/app/hook", ""]}}
    manifests = render_manifests(
        helm_runner,
        values={"lifecycle": {"preStop": handler}},
    )

    assert get_primary_container(manifests)["lifecycle"] == {"preStop": handler}


@pytest.mark.parametrize(
    "port",
    [
        pytest.param("http", id="letters"),
        pytest.param("http-2", id="internal-hyphen"),
        pytest.param("2-http", id="leading-number"),
        pytest.param("abcdefghijklmno", id="maximum-length"),
    ],
)
def test_http_lifecycle_allows_valid_named_ports(
    helm_runner,
    port: str,
) -> None:
    """Allow named ports accepted by Kubernetes."""

    handler = {"httpGet": {"path": "/drain", "port": port}}
    manifests = render_manifests(
        helm_runner,
        values={"lifecycle": {"preStop": handler}},
    )

    assert get_primary_container(manifests)["lifecycle"] == {"preStop": handler}


def test_legacy_extra_container_lifecycle_remains_supported(
    helm_runner,
) -> None:
    """Keep existing extraContainerProps lifecycle configurations working."""

    lifecycle = {"preStop": {"exec": {"command": ["/app/legacy-drain"]}}}
    manifests = render_manifests(
        helm_runner,
        values={"extraContainerProps": {"lifecycle": lifecycle}},
    )

    assert get_primary_container(manifests)["lifecycle"] == lifecycle


def test_structured_and_legacy_lifecycle_cannot_be_combined(
    helm_runner,
) -> None:
    """Fail clearly instead of rendering duplicate lifecycle YAML keys."""

    values = {
        "lifecycle": {"preStop": {"exec": {"command": ["/app/drain"]}}},
        "extraContainerProps": {
            "lifecycle": {
                "preStop": {"exec": {"command": ["/app/legacy-drain"]}}
            }
        },
    }

    with pytest.raises(
        HelmTemplateError,
        match="Set either lifecycle or extraContainerProps.lifecycle",
    ):
        render_chart(helm_runner, CHART, values=values)


@pytest.mark.parametrize(
    "strategy",
    [
        pytest.param({"type": "BlueGreen"}, id="unsupported-type"),
        pytest.param(
            {"type": "Recreate", "rollingUpdate": {"maxSurge": 1}},
            id="recreate-with-rolling-fields",
        ),
        pytest.param(
            {"type": "RollingUpdate", "batchSize": 1},
            id="unknown-property",
        ),
        pytest.param(
            {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxSurge": "one"},
            },
            id="malformed-percentage",
        ),
        pytest.param(
            {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": -1},
            },
            id="negative-value",
        ),
    ],
)
def test_deployment_strategy_rejects_invalid_values(
    helm_runner,
    strategy: dict[str, Any],
) -> None:
    """Reject strategy shapes Kubernetes cannot apply safely."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"deployment": {"strategy": strategy}},
        )


@pytest.mark.parametrize(
    ("max_surge", "max_unavailable"),
    [
        pytest.param(0, 0, id="integers"),
        pytest.param("0%", "0%", id="percentages"),
        pytest.param(0, "0%", id="mixed"),
        pytest.param("00%", 0, id="zero-padded-percentage"),
    ],
)
def test_rolling_update_requires_some_pod_movement(
    helm_runner,
    max_surge: int | str,
    max_unavailable: int | str,
) -> None:
    """Reject a rollout that can neither add nor remove a pod."""

    strategy = {
        "type": "RollingUpdate",
        "rollingUpdate": {
            "maxSurge": max_surge,
            "maxUnavailable": max_unavailable,
        },
    }

    with pytest.raises(
        HelmTemplateError,
        match="cannot set both maxSurge and maxUnavailable to zero",
    ):
        render_chart(
            helm_runner,
            CHART,
            values={"deployment": {"strategy": strategy}},
        )


@pytest.mark.parametrize(
    "deployment",
    [
        pytest.param({"minReadySeconds": -1}, id="negative-min-ready"),
        pytest.param({"progressDeadlineSeconds": 0}, id="zero-deadline"),
        pytest.param(
            {"minReadySeconds": 30, "progressDeadlineSeconds": 30},
            id="deadline-equals-min-ready",
        ),
        pytest.param(
            {"minReadySeconds": 30, "progressDeadlineSeconds": 20},
            id="deadline-below-min-ready",
        ),
        pytest.param(
            {"minReadySeconds": 600},
            id="default-deadline-equals-min-ready",
        ),
    ],
)
def test_rollout_timing_rejects_invalid_values(
    helm_runner,
    deployment: dict[str, int],
) -> None:
    """Reject invalid or internally inconsistent rollout timing."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"deployment": deployment},
        )


@pytest.mark.parametrize(
    "lifecycle",
    [
        pytest.param({"preStop": {}}, id="empty-handler"),
        pytest.param(
            {
                "preStop": {
                    "exec": {"command": ["/app/drain"]},
                    "sleep": {"seconds": 5},
                }
            },
            id="multiple-actions",
        ),
        pytest.param(
            {"preStop": {"exec": {"command": []}}},
            id="empty-command",
        ),
        pytest.param(
            {"preStop": {"httpGet": {"path": "/drain"}}},
            id="http-get-without-port",
        ),
        pytest.param(
            {"beforeStop": {"sleep": {"seconds": 5}}},
            id="unknown-phase",
        ),
        pytest.param(
            {"preStop": {"custom": {"command": "drain"}}},
            id="unknown-action",
        ),
    ],
)
def test_lifecycle_rejects_invalid_values(
    helm_runner,
    lifecycle: dict[str, Any],
) -> None:
    """Reject malformed lifecycle phases and handlers through the schema."""

    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values={"lifecycle": lifecycle})


@pytest.mark.parametrize(
    "port",
    [
        pytest.param("HTTP", id="uppercase"),
        pytest.param("8080", id="no-letter"),
        pytest.param("http_port", id="underscore"),
        pytest.param("abcdefghijklmnop", id="too-long"),
        pytest.param("-http", id="leading-hyphen"),
        pytest.param("http-", id="trailing-hyphen"),
        pytest.param("http--admin", id="adjacent-hyphens"),
    ],
)
def test_http_lifecycle_rejects_invalid_named_ports(
    helm_runner,
    port: str,
) -> None:
    """Reject named ports Kubernetes would refuse at admission."""

    lifecycle = {"preStop": {"httpGet": {"path": "/drain", "port": port}}}

    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values={"lifecycle": lifecycle})
