"""Environment reload annotation tests for universal-chart."""

from __future__ import annotations

import pytest

from .chart_test_utils import render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifest

RELOAD_ANNOTATION = "reloader.stakater.com/auto"


def _deployment_annotations(
    helm_runner,
    values: dict[str, object],
) -> dict[str, str]:
    """Render Deployment metadata annotations."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values=values,
    )
    return deployment["metadata"].get("annotations", {})


def test_reloader_is_disabled_by_default(helm_runner) -> None:
    """Keep existing environment inputs from changing rendered Deployments."""

    annotations = _deployment_annotations(
        helm_runner,
        {
            "awsEnvSecrets": {
                "env_secret_name": "aws-env",
                "externalSecret": {"secretPath": "apps/example"},
            },
            "extraEnvSecrets": ["database"],
            "extraEnvConfigmaps": ["application-config"],
        },
    )

    assert RELOAD_ANNOTATION not in annotations


@pytest.mark.parametrize(
    "input_values",
    [
        pytest.param({}, id="no-inputs"),
        pytest.param({"extraEnvSecrets": ["database"]}, id="secret"),
        pytest.param(
            {"extraEnvConfigmaps": ["application-config"]},
            id="configmap",
        ),
    ],
)
def test_reloader_enables_automatic_discovery(
    helm_runner,
    input_values: dict[str, object],
) -> None:
    """Let Reloader discover referenced Secrets and ConfigMaps."""

    annotations = _deployment_annotations(
        helm_runner,
        {
            "reloader": {"enabled": True},
            **input_values,
        },
    )

    assert annotations[RELOAD_ANNOTATION] == "true"


def test_reloader_preserves_deployment_annotations(helm_runner) -> None:
    """Add automatic discovery without dropping caller metadata."""

    annotations = _deployment_annotations(
        helm_runner,
        {
            "reloader": {"enabled": True},
            "extraEnvSecrets": ["database"],
            "extraEnvConfigmaps": ["application-config"],
            "deployment": {
                "annotations": {"example.com/owner": "platform"},
            },
        },
    )

    assert annotations == {
        "example.com/owner": "platform",
        RELOAD_ANNOTATION: "true",
    }


@pytest.mark.parametrize("enabled", [False, True])
def test_explicit_reload_annotation_takes_precedence(
    helm_runner,
    enabled: bool,
) -> None:
    """Preserve the caller-managed setting in either mode."""

    annotations = _deployment_annotations(
        helm_runner,
        {
            "reloader": {"enabled": enabled},
            "deployment": {
                "annotations": {
                    RELOAD_ANNOTATION: "false",
                },
            },
        },
    )

    assert annotations[RELOAD_ANNOTATION] == "false"


@pytest.mark.parametrize("enabled", ["true", 1, []])
def test_reloader_rejects_non_boolean_enabled_values(
    helm_runner,
    enabled: object,
) -> None:
    """Reject values that Helm would otherwise coerce by truthiness."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"reloader": {"enabled": enabled}},
        )
