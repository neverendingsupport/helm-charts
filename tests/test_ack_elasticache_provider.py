"""Unit tests for the ACK ElastiCache provider chart."""

from __future__ import annotations

import base64
import json
import re

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    load_manifests,
    manifests_by_name,
    render_chart,
)

CHART = ChartContext("ack-elasticache-provider")


def test_chart_renders_replication_group_with_minimal_values(
    helm_runner,
) -> None:
    """Ensure the default auth mode renders a no-auth cache setup."""

    rendered = render_chart(helm_runner, CHART)
    manifests = load_manifests(rendered)

    secret = get_manifest(manifests, "Secret")
    replication_group = get_manifest(manifests, "ReplicationGroup")
    assert get_manifest(manifests, "Secret")
    assert all(m.get("kind") != "Password" for m in manifests)
    assert all(m.get("kind") != "ExternalSecret" for m in manifests)
    assert secret["stringData"]["CACHE_USERNAME"] == "default"
    assert secret["stringData"]["CACHE_PASSWORD"] == ""
    assert secret["stringData"]["CACHE_PORT"] == "6379"
    assert secret["stringData"]["CACHE_TLS"] == "false"
    assert secret["stringData"]["CACHE_URL"] == ""
    assert secret["stringData"]["CACHE_AUTH_URL"] == ""
    assert replication_group["spec"]["replicationGroupID"] == "sample-cache"
    assert replication_group["spec"]["replicasPerNodeGroup"] == 0
    assert "authToken" not in replication_group["spec"]


def test_replication_group_supports_translated_cache_cluster_fields(
    helm_runner,
) -> None:
    """Ensure important ReplicationGroup spec fields can be configured."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "replicationGroupID": "dev-registry-cache",
            "description": "Replication group for dev-registry-cache",
            "engine": "redis",
            "engineVersion": "6.2.6",
            "cacheNodeType": "cache.t2.micro",
            "numNodeGroups": 1,
            "replicasPerNodeGroup": 0,
            "preferredCacheClusterAZs": ["us-west-2c"],
            "preferredMaintenanceWindow": "sun:05:00-sun:09:00",
            "cacheSubnetGroupName": "dev-registry-cache-subnet-group",
            "securityGroupIDs": ["sg-08dd4b4ff0fdf2f99"],
            "snapshotRetentionLimit": 0,
            "snapshotWindow": "09:00-12:00",
            "networkType": "ipv4",
            "ipDiscovery": "ipv4",
            "port": 6379,
            "atRestEncryptionEnabled": True,
            "transitEncryptionEnabled": True,
        },
    )
    replication_group = get_manifest(
        load_manifests(rendered), "ReplicationGroup"
    )

    assert (
        replication_group["spec"]["replicationGroupID"] == "dev-registry-cache"
    )
    assert replication_group["spec"]["preferredCacheClusterAZs"] == [
        "us-west-2c"
    ]
    assert replication_group["spec"]["securityGroupIDs"] == [
        "sg-08dd4b4ff0fdf2f99"
    ]
    assert replication_group["spec"]["port"] == 6379
    assert replication_group["spec"]["atRestEncryptionEnabled"] is True
    assert replication_group["spec"]["transitEncryptionEnabled"] is True


def test_valkey_engine_uses_cache_connection_secret_keys(
    helm_runner,
) -> None:
    """Ensure Valkey renders engine-agnostic connection secret keys."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "engine": "valkey",
            "engineVersion": "7.2",
            "auth.mode": "password",
        },
    )
    manifests = load_manifests(rendered)
    replication_group = get_manifest(manifests, "ReplicationGroup")
    external_secret = get_manifest(manifests, "ExternalSecret")
    exports = [m for m in manifests if m.get("kind") == "FieldExport"]

    assert replication_group["spec"]["engine"] == "valkey"
    assert replication_group["spec"]["engineVersion"] == "7.2"
    assert replication_group["spec"]["authToken"] == {
        "name": "ack-elasticache-provider-connection",
        "key": "CACHE_PASSWORD",
    }
    assert external_secret["spec"]["data"][0]["secretKey"] == ("CACHE_PASSWORD")

    template_data = external_secret["spec"]["target"]["template"]["data"]
    assert set(template_data) == {
        "CACHE_USERNAME",
        "CACHE_PORT",
        "CACHE_TLS",
        "CACHE_URL",
        "CACHE_AUTH_URL",
    }
    assert {item["spec"]["to"]["key"] for item in exports} == {
        "CACHE_HOST",
        "CACHE_PORT",
        "CACHE_ARN",
    }


def test_connection_secret_key_overrides_render_related_resources(
    helm_runner,
) -> None:
    """Ensure explicit key overrides render in related resources."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "engine": "valkey",
            "fieldExport.mappings": [
                {
                    "name": "host",
                    "path": ".status.nodeGroups.0.primaryEndpoint.address",
                    "key": "CUSTOM_HOST",
                },
                {
                    "name": "port",
                    "path": ".status.nodeGroups.0.primaryEndpoint.port",
                    "key": "CUSTOM_PORT",
                },
                {
                    "name": "arn",
                    "path": ".status.ackResourceMetadata.arn",
                    "key": "CUSTOM_ARN",
                },
            ],
            "pushSecret.enabled": True,
            "pushSecret.sourceKey": "CUSTOM_HOST",
            "pushSecret.target.provider": "aws-secrets-manager",
            "pushSecret.target.name": "aws/elasticache/valkey",
            "pushSecret.target.type": "connection",
        },
    )
    manifests = load_manifests(rendered)
    exports = [m for m in manifests if m.get("kind") == "FieldExport"]
    push_secret = get_manifest(manifests, "PushSecret")

    assert {item["spec"]["to"]["key"] for item in exports} == {
        "CUSTOM_HOST",
        "CUSTOM_PORT",
        "CUSTOM_ARN",
    }
    assert push_secret["spec"]["data"][0]["match"]["secretKey"] == (
        "CUSTOM_HOST"
    )


def test_resource_name_and_annotations_render(helm_runner) -> None:
    """Ensure metadata overrides are applied to the ReplicationGroup."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "resourceName": "custom-cache",
            "annotations": {"example.com/test": "true"},
        },
    )
    replication_group = get_manifest(
        load_manifests(rendered), "ReplicationGroup"
    )

    assert replication_group["metadata"]["name"] == "custom-cache"
    assert (
        replication_group["metadata"]["annotations"]["example.com/test"]
        == "true"
    )


def test_field_export_and_push_secret_options(helm_runner) -> None:
    """Ensure field exports and PushSecret honor value overrides."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "connectionSecret.name": "cache-connection",
            "pushSecret.enabled": True,
            "pushSecret.target.provider": "aws-secrets-manager",
            "pushSecret.target.name": "aws/elasticache/redis",
            "pushSecret.target.type": "connection",
        },
    )
    manifests = load_manifests(rendered)
    exports = [m for m in manifests if m.get("kind") == "FieldExport"]
    push_secret = get_manifest(manifests, "PushSecret")

    assert len(exports) == 3
    assert all(
        item["spec"]["to"]["name"] == "cache-connection" for item in exports
    )
    assert (
        push_secret["spec"]["selector"]["secret"]["name"] == "cache-connection"
    )


def test_generated_password_backs_auth_token_reference(helm_runner) -> None:
    """Ensure a generated password is also used for spec.authToken."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "auth.mode": "password",
            "connectionSecret.name": "cache-connection",
            "auth.username": "default",
            "auth.password.key": "REDIS_PASSWORD",
        },
    )
    manifests = load_manifests(rendered)
    replication_group = get_manifest(manifests, "ReplicationGroup")
    external_secret = get_manifest(manifests, "ExternalSecret")

    assert replication_group["spec"]["authToken"] == {
        "name": "cache-connection",
        "key": "REDIS_PASSWORD",
    }
    assert external_secret["spec"]["data"][0]["secretKey"] == "REDIS_PASSWORD"
    template_data = external_secret["spec"]["target"]["template"]["data"]
    assert template_data["CACHE_USERNAME"] == "default"
    assert template_data["CACHE_PORT"] == "6379"
    assert template_data["CACHE_TLS"] == "false"
    assert template_data["CACHE_URL"] == ""
    assert template_data["CACHE_AUTH_URL"] == ""


def test_secret_ref_mode_skips_password_generator(helm_runner) -> None:
    """Ensure secretRef omits the generator and uses the provided secret."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "auth.mode": "secretRef",
            "auth.existingSecret.name": "elasticache-auth",
            "auth.existingSecret.key": "token",
            "auth.existingSecret.namespace": "shared-secrets",
        },
    )
    manifests = load_manifests(rendered)
    secret = get_manifest(manifests, "Secret")
    replication_group = get_manifest(manifests, "ReplicationGroup")

    assert all(m.get("kind") != "Password" for m in manifests)
    assert all(m.get("kind") != "ExternalSecret" for m in manifests)
    assert secret["stringData"]["CACHE_PASSWORD"] == ""
    assert replication_group["spec"]["authToken"] == {
        "name": "elasticache-auth",
        "key": "token",
        "namespace": "shared-secrets",
    }


def test_disabled_mode_can_be_set_explicitly(helm_runner) -> None:
    """Ensure disabled auth omits authToken even when set explicitly."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"auth.mode": "disabled"},
    )
    manifests = load_manifests(rendered)
    secret = get_manifest(manifests, "Secret")
    replication_group = get_manifest(manifests, "ReplicationGroup")

    assert all(m.get("kind") != "Password" for m in manifests)
    assert all(m.get("kind") != "ExternalSecret" for m in manifests)
    assert secret["stringData"]["CACHE_PASSWORD"] == ""
    assert "authToken" not in replication_group["spec"]


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


def test_sequenced_connection_renders_hook_jobs(helm_runner) -> None:
    """Ensure sequenced mode owns secret creation and endpoint syncing."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "sequencedConnection.enabled": True,
            "auth.mode": "password",
            "connectionSecret.name": "cache-connection",
            "transitEncryptionEnabled": True,
        },
    )
    manifests = load_manifests(rendered)
    replication_group = get_manifest(manifests, "ReplicationGroup")
    service_account = get_manifest(manifests, "ServiceAccount")
    role = get_manifest(manifests, "Role")
    role_binding = get_manifest(manifests, "RoleBinding")
    jobs = manifests_by_name(manifests, "Job")

    assert all(m.get("kind") != "Secret" for m in manifests)
    assert all(m.get("kind") != "FieldExport" for m in manifests)
    assert all(m.get("kind") != "Password" for m in manifests)
    assert all(m.get("kind") != "ExternalSecret" for m in manifests)
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
    assert replication_group["spec"]["authToken"] == {
        "name": "cache-connection",
        "key": "CACHE_PASSWORD",
    }
    assert service_account["metadata"]["annotations"][
        "argocd.argoproj.io/hook"
    ] == ("PreSync")
    assert role["rules"][0]["resources"] == ["secrets"]
    assert (
        role_binding["subjects"][0]["name"]
        == service_account["metadata"]["name"]
    )
    assert len(jobs) == 2

    bootstrap_job = jobs[f"{CHART.release}-bootstrap-secret"]
    sync_job = jobs[f"{CHART.release}-sync-connection"]

    bootstrap_script = bootstrap_job["spec"]["template"]["spec"]["containers"][
        0
    ]["args"][0]
    sync_script = sync_job["spec"]["template"]["spec"]["containers"][0]["args"][
        0
    ]

    assert 'username_key="CACHE_USERNAME"' in bootstrap_script
    assert 'password_key="CACHE_PASSWORD"' in bootstrap_script
    assert 'tls_key="CACHE_TLS"' in bootstrap_script
    assert '"${tls_key}":"true"' in bootstrap_script
    assert 'url_key="CACHE_URL"' in sync_script
    assert 'auth_url_key="CACHE_AUTH_URL"' in sync_script
    assert 'tls_key="CACHE_TLS"' in sync_script
    assert '"${tls_key}":"true"' in sync_script
    assert "kubectl create -f" in bootstrap_script
    assert "replicationgroups.elasticache.services.k8s.aws" in sync_script
    assert (
        sync_job["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]
        == "20"
    )


def test_sequenced_valkey_connection_uses_cache_keys(helm_runner) -> None:
    """Ensure sequenced Valkey mode writes engine-agnostic secret keys."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "engine": "valkey",
            "sequencedConnection.enabled": True,
            "auth.mode": "password",
            "connectionSecret.name": "cache-connection",
        },
    )
    manifests = load_manifests(rendered)
    replication_group = get_manifest(manifests, "ReplicationGroup")
    jobs = manifests_by_name(manifests, "Job")

    assert replication_group["spec"]["authToken"] == {
        "name": "cache-connection",
        "key": "CACHE_PASSWORD",
    }

    bootstrap_job = jobs[f"{CHART.release}-bootstrap-secret"]
    sync_job = jobs[f"{CHART.release}-sync-connection"]

    bootstrap_script = bootstrap_job["spec"]["template"]["spec"]["containers"][
        0
    ]["args"][0]
    sync_script = sync_job["spec"]["template"]["spec"]["containers"][0]["args"][
        0
    ]

    assert 'username_key="CACHE_USERNAME"' in bootstrap_script
    assert 'password_key="CACHE_PASSWORD"' in bootstrap_script
    assert 'host_key="CACHE_HOST"' in bootstrap_script
    assert 'url_key="CACHE_URL"' in sync_script
    assert 'auth_url_key="CACHE_AUTH_URL"' in sync_script
    assert 'arn_key="CACHE_ARN"' in sync_script


def test_sequenced_connection_clears_removed_reflector_annotations(
    helm_runner,
) -> None:
    """Ensure sequenced mode nulls reflector annotations to remove."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "sequencedConnection.enabled": True,
            "auth.mode": "password",
            "connectionSecret.name": "cache-connection",
        },
    )
    manifests = load_manifests(rendered)
    bootstrap_job = get_manifest(
        manifests, "Job", name=f"{CHART.release}-bootstrap-secret"
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
