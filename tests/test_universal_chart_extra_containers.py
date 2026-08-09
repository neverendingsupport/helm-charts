"""Extra (sidecar) container tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import HelmTemplateError
from .chart_test_utils import get_manifest
from .universal_chart_test_utils import render_manifests

SIDECAR_IMAGE = {"repository": "ghcr.io/example/sidecar", "tag": "9.9.9"}


def _sidecar(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid extraContainers entry with overrides."""

    entry: dict[str, Any] = {"name": "sidecar", "image": dict(SIDECAR_IMAGE)}
    entry.update(overrides)
    return entry


def _pod_spec(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the Deployment pod spec."""

    deployment = get_manifest(manifests, "Deployment")
    return deployment["spec"]["template"]["spec"]


def _container(
    manifests: list[dict[str, Any]],
    name: str,
    *,
    init: bool = False,
) -> dict[str, Any]:
    """Return one container from the pod spec by name."""

    key = "initContainers" if init else "containers"
    containers = _pod_spec(manifests).get(key, [])
    for container in containers:
        if container["name"] == name:
            return container
    raise AssertionError(f"Container {name} not found in {key}")


def test_sidecar_renders_after_main_container(helm_runner) -> None:
    """Keep the main container first so kubectl defaults stay stable."""

    manifests = render_manifests(
        helm_runner,
        values={"extraContainers": [_sidecar()]},
    )
    containers = _pod_spec(manifests)["containers"]

    assert [c["name"] for c in containers] == ["universal-chart", "sidecar"]
    assert containers[1]["image"] == "ghcr.io/example/sidecar:9.9.9"


def test_sidecar_uses_chart_wide_pull_policy(helm_runner) -> None:
    """Apply the shared image.pullPolicy to sidecar containers."""

    manifests = render_manifests(
        helm_runner,
        values={
            "image.pullPolicy": "IfNotPresent",
            "extraContainers": [_sidecar()],
        },
    )

    sidecar = _container(manifests, "sidecar")
    assert sidecar["imagePullPolicy"] == "IfNotPresent"


def test_sidecar_image_renders_digest_reference(helm_runner) -> None:
    """Render repository@digest when the entry selects a digest."""

    digest = "sha256:" + "ab" * 32
    manifests = render_manifests(
        helm_runner,
        values={
            "extraContainers": [
                _sidecar(
                    image={
                        "repository": "ghcr.io/example/sidecar",
                        "digest": digest,
                    }
                )
            ]
        },
    )

    sidecar = _container(manifests, "sidecar")
    assert sidecar["image"] == f"ghcr.io/example/sidecar@{digest}"


def test_sidecar_inherits_env_and_env_from_by_default(helm_runner) -> None:
    """Copy the main container environment into inheriting sidecars."""

    manifests = render_manifests(
        helm_runner,
        values={
            "extraEnvVars": {"SHARED": "base"},
            "awsEnvSecrets.externalSecret.secretPath": "/example/app",
            "extraContainers": [_sidecar()],
        },
    )

    sidecar = _container(manifests, "sidecar")
    env = {entry["name"]: entry.get("value") for entry in sidecar["env"]}
    assert env["SHARED"] == "base"
    assert env["REDIS_ENABLED"] == "false"
    assert {"secretRef": {"name": "aws-env"}} in sidecar["envFrom"]


def test_sidecar_env_merges_and_overrides_inherited_values(
    helm_runner,
) -> None:
    """Merge sidecar env on top of the inherited environment."""

    manifests = render_manifests(
        helm_runner,
        values={
            "extraEnvVars": {"SHARED": "base", "OVERRIDE_ME": "original"},
            "extraContainers": [
                _sidecar(
                    env={"OVERRIDE_ME": "overridden", "OWN_VAR": "yes"},
                )
            ],
        },
    )

    sidecar = _container(manifests, "sidecar")
    env = {entry["name"]: entry.get("value") for entry in sidecar["env"]}
    assert env["SHARED"] == "base"
    assert env["OVERRIDE_ME"] == "overridden"
    assert env["OWN_VAR"] == "yes"
    names = [entry["name"] for entry in sidecar["env"]]
    assert names.count("OVERRIDE_ME") == 1


def test_sidecar_inherit_env_false_isolates_environment(helm_runner) -> None:
    """Drop the inherited env and envFrom when inheritEnv is false."""

    manifests = render_manifests(
        helm_runner,
        values={
            "extraEnvVars": {"SHARED": "base"},
            "awsEnvSecrets.externalSecret.secretPath": "/example/app",
            "extraContainers": [
                _sidecar(
                    inheritEnv=False,
                    env={"OWN_VAR": "yes"},
                    envFromSecrets=["own-secret"],
                )
            ],
        },
    )

    sidecar = _container(manifests, "sidecar")
    env = {entry["name"]: entry.get("value") for entry in sidecar["env"]}
    assert env == {"OWN_VAR": "yes"}
    assert sidecar["envFrom"] == [{"secretRef": {"name": "own-secret"}}]


def test_sidecar_volume_mounts_merge_and_override_by_path(
    helm_runner,
) -> None:
    """Merge sidecar mounts over inherited mounts, keyed by mountPath."""

    manifests = render_manifests(
        helm_runner,
        values={
            "volumeMounts": [
                {"name": "shared", "mountPath": "/scratch"},
                {"name": "shared", "mountPath": "/config"},
            ],
            "extraContainers": [
                _sidecar(
                    volumeMounts=[
                        {
                            "name": "shared",
                            "mountPath": "/config",
                            "readOnly": True,
                        }
                    ],
                )
            ],
        },
    )

    sidecar = _container(manifests, "sidecar")
    mounts = {m["mountPath"]: m for m in sidecar["volumeMounts"]}
    assert set(mounts) == {"/scratch", "/config"}
    assert mounts["/config"]["readOnly"] is True


def test_sidecar_inherit_volume_mounts_false_uses_own_mounts(
    helm_runner,
) -> None:
    """Drop inherited mounts when inheritVolumeMounts is false."""

    manifests = render_manifests(
        helm_runner,
        values={
            "volumeMounts": [{"name": "shared", "mountPath": "/scratch"}],
            "extraContainers": [
                _sidecar(
                    inheritVolumeMounts=False,
                    volumeMounts=[{"name": "own", "mountPath": "/own"}],
                )
            ],
        },
    )

    sidecar = _container(manifests, "sidecar")
    assert sidecar["volumeMounts"] == [{"name": "own", "mountPath": "/own"}]


def test_sidecar_security_context_inherits_then_replaces(helm_runner) -> None:
    """Inherit the top-level securityContext until the entry sets one."""

    values: dict[str, Any] = {
        "securityContext": {"runAsNonRoot": True, "runAsUser": 1000},
        "extraContainers": [
            _sidecar(),
            _sidecar(name="custom", securityContext={"runAsUser": 2000}),
        ],
    }
    manifests = render_manifests(helm_runner, values=values)

    inherited = _container(manifests, "sidecar")
    replaced = _container(manifests, "custom")
    assert inherited["securityContext"] == {
        "runAsNonRoot": True,
        "runAsUser": 1000,
    }
    assert replaced["securityContext"] == {"runAsUser": 2000}


def test_sidecar_probes_and_ports_render(helm_runner) -> None:
    """Render per-sidecar probes and ports."""

    manifests = render_manifests(
        helm_runner,
        values={
            "extraContainers": [
                _sidecar(
                    ports=[{"name": "metrics", "containerPort": 9090}],
                    readinessProbe={
                        "httpGet": {"path": "/ready", "port": "metrics"}
                    },
                    livenessProbe={
                        "httpGet": {"path": "/live", "port": "metrics"}
                    },
                )
            ]
        },
    )

    sidecar = _container(manifests, "sidecar")
    assert sidecar["ports"] == [
        {"name": "metrics", "containerPort": 9090, "protocol": "TCP"}
    ]
    assert sidecar["readinessProbe"]["httpGet"]["path"] == "/ready"
    assert sidecar["livenessProbe"]["httpGet"]["path"] == "/live"


def test_native_sidecar_renders_as_restarting_init_container(
    helm_runner,
) -> None:
    """Render nativeSidecar entries as initContainers with restartPolicy."""

    manifests = render_manifests(
        helm_runner,
        values={"extraContainers": [_sidecar(nativeSidecar=True)]},
    )
    pod_spec = _pod_spec(manifests)

    assert [c["name"] for c in pod_spec["containers"]] == ["universal-chart"]
    sidecar = _container(manifests, "sidecar", init=True)
    assert sidecar["restartPolicy"] == "Always"


def test_native_sidecar_precedes_legacy_init_containers(helm_runner) -> None:
    """Order native sidecars before legacy init containers."""

    manifests = render_manifests(
        helm_runner,
        values={
            "initContainers": [{"image": "amazon/aws-cli:latest"}],
            "extraContainers": [_sidecar(nativeSidecar=True)],
        },
    )
    init_names = [
        c["name"] for c in _pod_spec(manifests)["initContainers"]
    ]

    assert init_names == ["sidecar", "init-universal-chart-0"]


def test_sidecar_extra_container_props_pass_through(helm_runner) -> None:
    """Merge extraContainerProps keys into the container spec."""

    manifests = render_manifests(
        helm_runner,
        values={
            "extraContainers": [
                _sidecar(extraContainerProps={"workingDir": "/srv"})
            ]
        },
    )

    sidecar = _container(manifests, "sidecar")
    assert sidecar["workingDir"] == "/srv"


@pytest.mark.parametrize(
    "extra_containers",
    [
        pytest.param([_sidecar(name="universal-chart")], id="main-container"),
        pytest.param([_sidecar(), _sidecar()], id="duplicate-sidecars"),
        pytest.param(
            [_sidecar(name="init-universal-chart-0", nativeSidecar=True)],
            id="generated-init-name",
        ),
    ],
)
def test_container_name_collisions_fail(
    helm_runner,
    extra_containers: list[dict[str, Any]],
) -> None:
    """Fail rendering when container names collide."""

    values: dict[str, Any] = {"extraContainers": extra_containers}
    if extra_containers[0]["name"].startswith("init-"):
        values["initContainers"] = [{"image": "amazon/aws-cli:latest"}]

    with pytest.raises(HelmTemplateError):
        render_manifests(helm_runner, values=values)


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(_sidecar(image={"repository": "x"}), id="no-tag"),
        pytest.param(
            _sidecar(
                image={
                    "repository": "x",
                    "tag": "1",
                    "digest": "sha256:" + "ab" * 32,
                }
            ),
            id="tag-and-digest",
        ),
        pytest.param(_sidecar(readinesProbe={}), id="typo-key"),
        pytest.param({"image": dict(SIDECAR_IMAGE)}, id="missing-name"),
    ],
)
def test_schema_rejects_invalid_entries(
    helm_runner,
    entry: dict[str, Any],
) -> None:
    """Reject malformed extraContainers entries at render time."""

    with pytest.raises(HelmTemplateError):
        render_manifests(helm_runner, values={"extraContainers": [entry]})
