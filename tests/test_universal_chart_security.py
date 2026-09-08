"""Restricted security profile behavior and override coverage."""

from __future__ import annotations

import pytest

from .chart_test_utils import get_manifest, load_manifests, render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifest, render_manifests


def test_security_profile_preserves_disabled_output(helm_runner) -> None:
    """Leave pod and container fields absent and keep the old token default."""

    manifests = render_manifests(helm_runner)
    pod = get_manifest(manifests, "Deployment")["spec"]["template"]["spec"]
    assert "securityContext" not in pod
    assert "securityContext" not in pod["containers"][0]
    assert "automountServiceAccountToken" not in pod
    assert get_manifest(manifests, "ServiceAccount")[
        "automountServiceAccountToken"
    ]


@pytest.mark.parametrize("automount", [True, None])
def test_security_profile_missing_from_legacy_values(
    helm_runner, automount
) -> None:
    """Render when reused old values lack the new profile block."""

    manifests = render_manifests(
        helm_runner,
        values={
            "securityProfile": None,
            "serviceAccount.automount": automount,
            "initContainers": [{"image": "example.com/init:1"}],
        },
    )
    pod = get_manifest(manifests, "Deployment")["spec"]["template"]["spec"]
    assert "automountServiceAccountToken" not in pod
    assert "securityContext" not in pod
    assert "securityContext" not in pod["containers"][0]
    assert "securityContext" not in pod["initContainers"][0]
    account = get_manifest(manifests, "ServiceAccount")
    assert account["automountServiceAccountToken"] is True


def test_security_profile_covers_main_and_init_containers(helm_runner) -> None:
    """Apply restrictions to both main and init containers."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={
            "securityProfile.enabled": True,
            "initContainers": [{"image": "example.com/init:1"}],
        },
    )
    pod = deployment["spec"]["template"]["spec"]
    assert pod["securityContext"] == {
        "runAsNonRoot": True,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    assert pod["automountServiceAccountToken"] is False
    for container in pod["containers"] + pod["initContainers"]:
        assert container["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
        }


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("create", [False, True])
@pytest.mark.parametrize("automount", [None, False, True])
def test_security_profile_token_precedence(
    helm_runner, enabled: bool, create: bool, automount: bool | None
) -> None:
    """Respect explicit booleans and protect pods using external accounts."""

    manifests = render_manifests(
        helm_runner,
        values={
            "securityProfile.enabled": enabled,
            "serviceAccount": {
                "create": create,
                "name": "application-account",
                "automount": automount,
            },
        },
    )
    expected = not enabled if automount is None else automount
    pod = get_manifest(manifests, "Deployment")["spec"]["template"]["spec"]
    assert pod["serviceAccountName"] == "application-account"
    if enabled:
        assert pod["automountServiceAccountToken"] is expected
    else:
        assert "automountServiceAccountToken" not in pod
    accounts = [doc for doc in manifests if doc["kind"] == "ServiceAccount"]
    assert len(accounts) == int(create)
    if create:
        assert accounts[0]["automountServiceAccountToken"] is expected


@pytest.mark.parametrize("enabled", [False, True])
def test_security_contexts_preserve_explicit_overrides(
    helm_runner, enabled
) -> None:
    """Preserve explicit overrides and unrelated security fields."""

    pod_context = {
        "runAsNonRoot": False,
        "runAsUser": 1001,
        "fsGroup": 2000,
        "seccompProfile": {"type": "Localhost", "localhostProfile": "app.json"},
    }
    container_context = {
        "allowPrivilegeEscalation": True,
        "capabilities": {"drop": [], "add": ["NET_BIND_SERVICE"]},
        "readOnlyRootFilesystem": True,
        "runAsNonRoot": False,
    }
    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={
            "securityProfile.enabled": enabled,
            "podSecurityContext": pod_context,
            "securityContext": container_context,
            "initContainers": [{"image": "example.com/init:1"}],
        },
    )
    pod = deployment["spec"]["template"]["spec"]
    assert pod["securityContext"] == pod_context
    for container in pod["containers"] + pod["initContainers"]:
        assert container["securityContext"] == container_context


def test_security_profile_merges_legacy_contexts_without_duplicate_keys(
    helm_runner,
) -> None:
    """Keep restrictions unless a per-container override replaces that field."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "securityProfile.enabled": True,
            "securityContext": {"readOnlyRootFilesystem": True},
            "extraContainerProps": {
                "securityContext": {"readOnlyRootFilesystem": False},
                "workingDir": "/app",
            },
            "initContainers": [
                {
                    "image": "example.com/init:1",
                    "extraContainerProps": {
                        "securityContext": {"capabilities": {"add": ["CHOWN"]}},
                        "workingDir": "/init",
                    },
                },
                {"image": "example.com/init-second:1"},
            ],
        },
    )
    pod = get_manifest(load_manifests(rendered), "Deployment")["spec"][
        "template"
    ]["spec"]
    assert rendered.count("securityContext:") == 4
    main, init = pod["containers"][0], pod["initContainers"][0]
    assert main["workingDir"] == "/app"
    assert init["workingDir"] == "/init"
    assert main["securityContext"]["readOnlyRootFilesystem"] is False
    assert init["securityContext"]["readOnlyRootFilesystem"] is True
    assert main["securityContext"]["capabilities"] == {"drop": ["ALL"]}
    assert init["securityContext"]["capabilities"] == {
        "drop": ["ALL"],
        "add": ["CHOWN"],
    }
    assert main["securityContext"]["allowPrivilegeEscalation"] is False
    assert init["securityContext"]["allowPrivilegeEscalation"] is False
    assert pod["initContainers"][1]["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
        "readOnlyRootFilesystem": True,
    }


@pytest.mark.parametrize("init", [False, True])
@pytest.mark.parametrize("context", ["invalid", False, 0, [], ""])
def test_security_profile_rejects_non_object_legacy_context(
    helm_runner, init, context
) -> None:
    """Reject a legacy override that cannot merge with the security baseline."""

    props = {"securityContext": context}
    values: dict[str, object] = {"securityProfile.enabled": True}
    if init:
        values["initContainers"] = [
            {"image": "example.com/init:1", "extraContainerProps": props}
        ]
    else:
        values["extraContainerProps"] = props
    with pytest.raises(
        HelmTemplateError, match="securityContext must be an object"
    ):
        render_chart(helm_runner, CHART, values=values)


@pytest.mark.parametrize(
    "values",
    [
        {"securityProfile": {"enabled": "true"}},
        {"securityProfile": {"enabled": 1}},
        {"securityProfile": {"unknown": True}},
        {"serviceAccount": {"automount": "false"}},
        {"serviceAccount": {"automount": 1}},
    ],
)
def test_security_profile_schema_rejects_invalid_values(
    helm_runner, values
) -> None:
    """Catch typoed profile keys and booleans before rendering."""

    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values=values)
