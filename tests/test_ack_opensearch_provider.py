"""Unit tests for the ACK OpenSearch provider chart."""

from __future__ import annotations

import base64
import json
import re

import pytest

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    load_manifests,
    render_chart,
)
from .conftest import HelmTemplateError

CHART = ChartContext("ack-opensearch-provider")
CURL_IMAGE = (
    "curlimages/curl:8.12.1@"
    "sha256:94e9e444bcba979c2ea12e27ae39bee4cd10bc7041a472c4727a558e213744e6"
)
KUBECTL_IMAGE = (
    "registry.k8s.io/kubectl:v1.34.1@"
    "sha256:59bafa07ff3a6d4b417e7633ddb9d79a9606ca98bf64bac080b3e65748669250"
)


def test_chart_renders_domain_with_defaults(helm_runner) -> None:
    """Ensure default values render core OpenSearch resources."""

    rendered = render_chart(helm_runner, CHART)
    manifests = load_manifests(rendered)

    assert get_manifest(manifests, "Domain")
    secret = get_manifest(manifests, "Secret")
    assert get_manifest(manifests, "Password")
    assert get_manifest(manifests, "ExternalSecret")
    assert secret["stringData"]["OPENSEARCH_USERNAME"] == "admin"
    assert secret["stringData"]["OPENSEARCH_PORT"] == "443"
    assert secret["stringData"]["OPENSEARCH_URL"] == ""
    assert secret["stringData"]["OPENSEARCH_AUTH_URL"] == ""


def test_domain_spec_supports_crd_fields(helm_runner) -> None:
    """Ensure Domain CRD spec fields can be configured via values."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "name": "prod-domain",
            "engineVersion": "OpenSearch_2.13",
            "clusterConfig": {
                "instanceType": "m6g.large.search",
                "instanceCount": 2,
            },
            "nodeToNodeEncryptionOptions.enabled": True,
            "offPeakWindowOptions": {"enabled": True},
        },
    )
    domain = get_manifest(load_manifests(rendered), "Domain")

    assert domain["spec"]["name"] == "prod-domain"
    assert domain["spec"]["clusterConfig"]["instanceCount"] == 2


def test_legacy_domain_values_still_render(helm_runner) -> None:
    """Ensure the prior nested domain values shape remains supported."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values_files=[CHART.fixtures_dir / "legacy-compat.yaml"],
        values={
            "domain.spec.engineVersion": "OpenSearch_2.13",
        },
    )
    domain = get_manifest(load_manifests(rendered), "Domain")

    assert domain["metadata"]["name"] == "legacy-resource"
    assert domain["metadata"]["annotations"]["example.com/test"] == "true"
    assert domain["spec"]["name"] == "legacy-domain"


def test_reflector_annotations_render(helm_runner) -> None:
    """Ensure reflector lists are rendered as secret annotations."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "reflector.enabled": True,
            "reflector.pushNamespaces": ["team-a", "team-b"],
            "reflector.allowedNamespaces": ["team-a", "team-c"],
        },
    )

    secret = get_manifest(load_manifests(rendered), "Secret")
    annotations = secret["metadata"]["annotations"]

    assert (
        annotations[
            "reflector.v1.k8s.emberstack.com/reflection-auto-namespaces"
        ]
        == "team-a,team-b"
    )
    assert (
        annotations[
            "reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces"
        ]
        == "team-a,team-c"
    )


def test_field_export_secret_name_override(helm_runner) -> None:
    """Ensure FieldExport targets follow secret name overrides."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"connectionSecret.name": "custom-connection"},
    )

    manifests = load_manifests(rendered)
    exports = [m for m in manifests if m.get("kind") == "FieldExport"]

    assert all(
        item["spec"]["to"]["name"] == "custom-connection" for item in exports
    )


def test_push_secret_renders_target_configuration(helm_runner) -> None:
    """Ensure PushSecret renders provider/name/type target configuration."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "pushSecret.enabled": True,
            "pushSecret.target.name": "aws/opensearch/domain",
            "pushSecret.target.provider": "aws-secrets-manager",
            "pushSecret.target.type": "connection",
            "pushSecret.sourceKey": "ARN",
        },
    )

    push_secret = get_manifest(load_manifests(rendered), "PushSecret")
    assert (
        push_secret["spec"]["secretStoreRefs"][0]["name"]
        == "aws-secrets-manager"
    )
    data = push_secret["spec"]["data"][0]["match"]
    assert data["secretKey"] == "ARN"
    assert data["remoteRef"]["remoteKey"] == "aws/opensearch/domain"
    assert data["remoteRef"]["property"] == "connection"


def test_irsa_auth_uses_empty_password(helm_runner) -> None:
    """Ensure IRSA mode uses empty password and no Password generator."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "auth.mode": "irsa",
            "auth.irsaRoleArn": "arn:aws:iam::123456789012:role/opensearch",
        },
    )
    manifests = load_manifests(rendered)
    secret = get_manifest(manifests, "Secret")

    assert 'OPENSEARCH_PASSWORD: ""' in rendered
    assert all(m.get("kind") != "Password" for m in manifests)
    assert (
        secret["stringData"]["AWS_ROLE_ARN"]
        == "arn:aws:iam::123456789012:role/opensearch"
    )
    assert secret["stringData"]["OPENSEARCH_PASSWORD"] == ""


def test_security_bootstrap_renders_role_and_mapping_payloads(
    helm_runner,
) -> None:
    """Ensure security bootstrap renders the expected role payloads."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "securityBootstrap.enabled": True,
            "securityRoles": [
                {
                    "name": "developer_debug_readonly",
                    "clusterPermissions": [
                        "cluster_composite_ops_ro",
                        "cluster_monitor",
                    ],
                    "indexPermissions": [
                        {
                            "indexPatterns": ["eol-engine-*"],
                            "allowedActions": [
                                "read",
                                "indices_monitor",
                                "view_index_metadata",
                            ],
                        }
                    ],
                }
            ],
            "securityRoleMappings": [
                {
                    "roleName": "developer_debug_readonly",
                    "backendRoles": [
                        "arn:aws:iam::523530333233:role/platform-dev"
                    ],
                }
            ],
        },
    )

    manifests = load_manifests(rendered)
    service_account = get_manifest(manifests, "ServiceAccount")
    role = get_manifest(manifests, "Role")
    role_binding = get_manifest(manifests, "RoleBinding")
    job = get_manifest(manifests, "Job")

    assert service_account["metadata"]["name"].endswith("security-bootstrap")
    assert role["rules"][0]["verbs"] == [
        "get",
        "create",
        "update",
        "patch",
    ]
    assert (
        role_binding["subjects"][0]["name"]
        == service_account["metadata"]["name"]
    )

    pod_spec = job["spec"]["template"]["spec"]
    assert pod_spec["initContainers"][0]["image"] == KUBECTL_IMAGE
    assert pod_spec["containers"][0]["image"] == CURL_IMAGE

    script = pod_spec["containers"][0]["args"][0]
    role_match = re.search(
        r'apply_role \\\n\s+"developer_debug_readonly" \\\n\s+\'([^\']+)\'',
        script,
    )
    assert role_match is not None
    role_payload = json.loads(
        base64.b64decode(role_match.group(1)).decode("utf-8")
    )
    assert role_payload == {
        "cluster_permissions": [
            "cluster_composite_ops_ro",
            "cluster_monitor",
        ],
        "index_permissions": [
            {
                "index_patterns": ["eol-engine-*"],
                "allowed_actions": [
                    "read",
                    "indices_monitor",
                    "view_index_metadata",
                ],
            }
        ],
    }

    mapping_match = re.search(
        (
            r'apply_role_mapping \\\n\s+"developer_debug_readonly"'
            r" \\\n\s+\'([^\']+)\'"
        ),
        script,
    )
    assert mapping_match is not None
    mapping_payload = json.loads(
        base64.b64decode(mapping_match.group(1)).decode("utf-8")
    )
    assert mapping_payload == {
        "backend_roles": ["arn:aws:iam::523530333233:role/platform-dev"]
    }


def test_global_image_repository_prefixes_bootstrap_images(
    helm_runner,
) -> None:
    """Ensure global.imageRepository prefixes bootstrap image defaults."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "global.imageRepository": (
                "523530333233.dkr.ecr.us-west-2.amazonaws.com/docker-hub"
            ),
            "securityBootstrap.enabled": True,
            "securityRoles": [{"name": "developer_debug_readonly"}],
            "sequencedConnection.enabled": True,
        },
    )

    manifests = load_manifests(rendered)
    jobs = [manifest for manifest in manifests if manifest.get("kind") == "Job"]
    job_images: list[str] = []
    for job in jobs:
        pod_spec = job["spec"]["template"]["spec"]
        job_images.extend(
            container["image"]
            for container in pod_spec.get("initContainers", [])
        )
        job_images.extend(
            container["image"] for container in pod_spec.get("containers", [])
        )

    assert (
        "523530333233.dkr.ecr.us-west-2.amazonaws.com/docker-hub/"
        f"{CURL_IMAGE}"
    ) in job_images
    assert (
        "523530333233.dkr.ecr.us-west-2.amazonaws.com/docker-hub/"
        f"{KUBECTL_IMAGE}"
    ) in job_images


def test_role_mapping_connection_secret_reflector_renders_metadata_only(
    helm_runner,
) -> None:
    """Ensure role mappings can create reflected metadata-only secrets."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "securityBootstrap.enabled": True,
            "securityRoles": [{"name": "developer_debug_readonly"}],
            "securityRoleMappings": [
                {
                    "roleName": "developer_debug_readonly",
                    "backendRoles": [
                        "arn:aws:iam::523530333233:role/eol-engine-write"
                    ],
                    "connectionSecret": {
                        "name": "eol-engine-write-opensearch-conninfo",
                        "reflector": {
                            "enabled": True,
                            "pushNamespaces": ["eol-engine-write"],
                            "allowedNamespaces": ["eol-engine-write"],
                        },
                    },
                }
            ],
        },
    )

    manifests = load_manifests(rendered)
    job = get_manifest(manifests, "Job")
    init_script = job["spec"]["template"]["spec"]["initContainers"][0]["args"][
        0
    ]

    assert "eol-engine-write-opensearch-conninfo" in init_script
    assert "--from-literal=OPENSEARCH_HOST=" in init_script
    assert "--from-literal=OPENSEARCH_PORT=" in init_script
    assert "--from-literal=OPENSEARCH_URL=" in init_script
    assert "--from-literal=OPENSEARCH_ARN=" in init_script
    assert "--from-literal=OPENSEARCH_USERNAME=" not in init_script
    assert "--from-literal=OPENSEARCH_PASSWORD=" not in init_script

    metadata_patch_match = re.search(
        r"echo '([^']+)' \| base64 -d > "
        r"/tmp/role-mapping-connection-developer-debug-readonly-metadata\.json",
        init_script,
    )
    assert metadata_patch_match is not None
    metadata_patch = json.loads(
        base64.b64decode(metadata_patch_match.group(1)).decode("utf-8")
    )
    assert metadata_patch["metadata"]["annotations"] == {
        "reflector.v1.k8s.emberstack.com/reflection-allowed": "true",
        "reflector.v1.k8s.emberstack.com/reflection-auto-enabled": "true",
        "reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces": (
            "eol-engine-write"
        ),
        "reflector.v1.k8s.emberstack.com/reflection-auto-namespaces": (
            "eol-engine-write"
        ),
    }


def test_application_users_render_bootstrap_and_password_resources(
    helm_runner,
) -> None:
    """Ensure application users render password resources and bootstrap."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "securityBootstrap.enabled": True,
            "securityRoles": [
                {
                    "name": "gorny_app_readwrite",
                    "clusterPermissions": [
                        "cluster_composite_ops",
                        "cluster_monitor",
                    ],
                    "indexPermissions": [
                        {
                            "indexPatterns": ["gorny-*"],
                            "allowedActions": [
                                "crud",
                                "create_index",
                                "manage",
                            ],
                        }
                    ],
                }
            ],
            "applicationUsers": [
                {
                    "name": "gorny-app",
                    "username": "gorny_app",
                    "roleName": "gorny_app_readwrite",
                    "password": {
                        "generate": True,
                        "secretName": "gorny-opensearch-app-auth",
                        "secretKey": "OPENSEARCH_PASSWORD",
                        "length": 40,
                        "digits": 10,
                        "symbols": 2,
                    },
                    "connectionSecret": {
                        "name": "gorny-opensearch-app-conninfo",
                        "reflector": {
                            "enabled": True,
                            "pushNamespaces": ["gorny-api", "gorny-worker"],
                            "allowedNamespaces": [
                                "gorny-api",
                                "gorny-worker",
                            ],
                        },
                    },
                }
            ],
        },
    )

    manifests = load_manifests(rendered)
    passwords = [m for m in manifests if m.get("kind") == "Password"]
    external_secrets = [
        m for m in manifests if m.get("kind") == "ExternalSecret"
    ]
    job = get_manifest(manifests, "Job")

    assert len(passwords) == 2
    assert any(
        password["spec"]
        == {
            "length": 40,
            "digits": 10,
            "symbols": 2,
            "noUpper": False,
            "allowRepeat": True,
        }
        for password in passwords
    )
    assert any(
        external_secret["spec"]["target"]["name"] == "gorny-opensearch-app-auth"
        for external_secret in external_secrets
    )

    pod_spec = job["spec"]["template"]["spec"]
    init_script = pod_spec["initContainers"][0]["args"][0]
    main_script = pod_spec["containers"][0]["args"][0]

    assert "gorny-opensearch-app-auth" in init_script
    assert "gorny-opensearch-app-conninfo" in init_script
    assert "application_user_password_gorny_app" in init_script
    assert 'kubectl patch secret "gorny-opensearch-app-conninfo"' in init_script
    assert "apply_application_user" in main_script
    assert '"gorny_app"' in main_script

    metadata_patch_match = re.search(
        r"echo '([^']+)' \| base64 -d > "
        r"/tmp/application-user-connection-gorny-app-metadata\.json",
        init_script,
    )
    assert metadata_patch_match is not None
    metadata_patch = json.loads(
        base64.b64decode(metadata_patch_match.group(1)).decode("utf-8")
    )
    assert metadata_patch["metadata"]["annotations"] == {
        "reflector.v1.k8s.emberstack.com/reflection-allowed": "true",
        (
            "reflector.v1.k8s.emberstack.com/" "reflection-allowed-namespaces"
        ): "gorny-api,gorny-worker",
        "reflector.v1.k8s.emberstack.com/reflection-auto-enabled": "true",
        (
            "reflector.v1.k8s.emberstack.com/" "reflection-auto-namespaces"
        ): "gorny-api,gorny-worker",
    }

    user_match = re.search(
        r'apply_application_user \\\n\s+"gorny_app" \\\n'
        r"\s+/work/application-user-password-gorny-app \\\n"
        r"\s+'([^']+)'",
        main_script,
    )
    assert user_match is not None
    role_names = json.loads(
        base64.b64decode(user_match.group(1)).decode("utf-8")
    )
    assert role_names == ["gorny_app_readwrite"]


def test_security_bootstrap_requires_password_auth(helm_runner) -> None:
    """Reject security bootstrap when auth.mode is not password."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "auth.mode": "irsa",
                "securityBootstrap.enabled": True,
                "securityRoles": [{"name": "developer_debug_readonly"}],
            },
        )


def test_security_bootstrap_allows_builtin_role_mappings(helm_runner) -> None:
    """Allow role mappings that target built-in OpenSearch roles."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "securityBootstrap.enabled": True,
            "securityRoleMappings": [
                {
                    "roleName": "opensearch_dashboards_user",
                    "backendRoles": ["infrastructure"],
                }
            ],
        },
    )

    job = get_manifest(load_manifests(rendered), "Job")
    script = job["spec"]["template"]["spec"]["containers"][0]["args"][0]
    mapping_match = re.search(
        (
            r'apply_role_mapping \\\n\s+"opensearch_dashboards_user"'
            r" \\\n\s+\'([^\']+)\'"
        ),
        script,
    )
    assert mapping_match is not None
    mapping_payload = json.loads(
        base64.b64decode(mapping_match.group(1)).decode("utf-8")
    )
    assert mapping_payload == {"backend_roles": ["infrastructure"]}


def test_application_users_require_existing_secret_name(helm_runner) -> None:
    """Reject non-generated application user passwords without a secret."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "securityBootstrap.enabled": True,
                "securityRoles": [{"name": "gorny_app_readwrite"}],
                "applicationUsers": [
                    {
                        "name": "gorny-app",
                        "username": "gorny_app",
                        "roleName": "gorny_app_readwrite",
                        "password": {"generate": False},
                    }
                ],
            },
        )


def test_application_users_reject_unknown_role_name(helm_runner) -> None:
    """Reject application users that point at an undefined role."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "securityBootstrap.enabled": True,
                "securityRoles": [{"name": "gorny_app_readwrite"}],
                "applicationUsers": [
                    {
                        "name": "gorny-app",
                        "username": "gorny_app",
                        "roleName": "missing-role",
                        "password": {
                            "generate": False,
                            "existingSecretRef": {
                                "name": "gorny-opensearch-app-auth"
                            },
                        },
                    }
                ],
            },
        )


def test_sequenced_connection_renders_hook_jobs(helm_runner) -> None:
    """Ensure sequenced mode owns secret creation and endpoint syncing."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "sequencedConnection.enabled": True,
            "connectionSecret.name": "domain-connection",
            "auth.mode": "password",
            "auth.password.key": "OPENSEARCH_PASSWORD",
        },
    )

    manifests = load_manifests(rendered)
    domain = get_manifest(manifests, "Domain")
    service_account = get_manifest(manifests, "ServiceAccount")
    role = get_manifest(manifests, "Role")
    role_binding = get_manifest(manifests, "RoleBinding")
    jobs = [m for m in manifests if m.get("kind") == "Job"]

    assert domain["spec"]["name"] == "sample-domain"
    assert all(m.get("kind") != "Secret" for m in manifests)
    assert all(m.get("kind") != "FieldExport" for m in manifests)
    assert all(m.get("kind") != "Password" for m in manifests)
    assert all(m.get("kind") != "ExternalSecret" for m in manifests)
    assert service_account["metadata"]["annotations"][
        "argocd.argoproj.io/hook"
    ] == ("PreSync")
    assert (
        service_account["metadata"]["annotations"][
            "argocd.argoproj.io/hook-delete-policy"
        ]
        == "BeforeHookCreation"
    )
    assert (
        role["metadata"]["annotations"]["argocd.argoproj.io/hook-delete-policy"]
        == "BeforeHookCreation"
    )
    assert (
        role_binding["metadata"]["annotations"][
            "argocd.argoproj.io/hook-delete-policy"
        ]
        == "BeforeHookCreation"
    )
    assert role["rules"][0]["resources"] == ["secrets"]
    assert (
        role_binding["subjects"][0]["name"]
        == service_account["metadata"]["name"]
    )
    assert len(jobs) == 2

    bootstrap_job = next(
        job
        for job in jobs
        if job["metadata"]["name"].endswith("bootstrap-secret")
    )
    sync_job = next(
        job
        for job in jobs
        if job["metadata"]["name"].endswith("sync-connection")
    )

    bootstrap_script = bootstrap_job["spec"]["template"]["spec"]["containers"][
        0
    ]["args"][0]
    sync_script = sync_job["spec"]["template"]["spec"]["containers"][0]["args"][
        0
    ]

    assert 'username_key="OPENSEARCH_USERNAME"' in bootstrap_script
    assert 'password_key="OPENSEARCH_PASSWORD"' in bootstrap_script
    assert 'url_key="OPENSEARCH_URL"' in sync_script
    assert 'auth_url_key="OPENSEARCH_AUTH_URL"' in sync_script
    assert "kubectl create -f" in bootstrap_script
    assert "domains.opensearchservice.services.k8s.aws" in sync_script
    assert ".status.ackResourceMetadata.arn" in sync_script
    assert (
        sync_job["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]
        == "20"
    )


def test_sequenced_connection_clears_removed_reflector_annotations(
    helm_runner,
) -> None:
    """Ensure sequenced mode nulls removed reflector annotations."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "sequencedConnection.enabled": True,
            "connectionSecret.name": "domain-connection",
            "auth.mode": "password",
            "auth.password.key": "OPENSEARCH_PASSWORD",
        },
    )

    manifests = load_manifests(rendered)
    bootstrap_job = next(
        job
        for job in manifests
        if job.get("kind") == "Job"
        and job["metadata"]["name"].endswith("bootstrap-secret")
    )
    bootstrap_script = bootstrap_job["spec"]["template"]["spec"]["containers"][
        0
    ]["args"][0]

    encoded_patch = re.search(
        r"echo '([^']+)' \| base64 -d > /tmp/secret-metadata-patch\.json",
        bootstrap_script,
    )
    assert encoded_patch is not None

    metadata_patch = json.loads(
        base64.b64decode(encoded_patch.group(1)).decode("utf-8")
    )
    annotations = metadata_patch["metadata"]["annotations"]

    assert (
        annotations["reflector.v1.k8s.emberstack.com/reflection-allowed"]
        is None
    )
    assert (
        annotations[
            "reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces"
        ]
        is None
    )
    assert (
        annotations["reflector.v1.k8s.emberstack.com/reflection-auto-enabled"]
        is None
    )
    assert (
        annotations[
            "reflector.v1.k8s.emberstack.com/reflection-auto-namespaces"
        ]
        is None
    )
