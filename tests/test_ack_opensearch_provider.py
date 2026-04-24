"""Unit tests for the ACK OpenSearch provider chart."""

from __future__ import annotations

import base64
import json
import re

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    load_manifests,
    render_chart,
)

CHART = ChartContext("ack-opensearch-provider")


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
    """Ensure sequenced mode nulls reflector annotations that should be removed."""

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
