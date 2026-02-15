"""Unit tests for the ACK DocumentDB provider chart."""

from __future__ import annotations

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    load_manifests,
    render_chart,
)

CHART = ChartContext("ack-documentdb-provider")


def test_chart_renders_with_defaults(helm_runner) -> None:
    rendered = render_chart(helm_runner, CHART)
    manifests = load_manifests(rendered)

    assert get_manifest(manifests, "DBCluster")
    assert get_manifest(manifests, "Secret")
    assert get_manifest(manifests, "Password")


def test_dbcluster_spec_supports_crd_fields(helm_runner) -> None:
    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "dbCluster.spec.dbClusterIdentifier": "prod-docdb",
            "dbCluster.spec.engineVersion": "5.0.0",
            "dbCluster.spec.masterUsername": "master",
            "dbCluster.spec.storageEncrypted": True,
            "dbCluster.spec.backupRetentionPeriod": 7,
        },
    )
    cluster = get_manifest(load_manifests(rendered), "DBCluster")

    assert cluster["spec"]["dbClusterIdentifier"] == "prod-docdb"
    assert cluster["spec"]["backupRetentionPeriod"] == 7


def test_field_export_and_push_secret_options(helm_runner) -> None:
    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "connectionSecret.name": "docdb-connection",
            "pushSecret.enabled": True,
            "pushSecret.target.provider": "aws-secrets-manager",
            "pushSecret.target.name": "aws/docdb/cluster",
            "pushSecret.target.type": "connection",
        },
    )
    manifests = load_manifests(rendered)
    exports = [m for m in manifests if m.get("kind") == "FieldExport"]
    push_secret = get_manifest(manifests, "PushSecret")

    assert len(exports) == 3
    assert all(e["spec"]["to"]["name"] == "docdb-connection" for e in exports)
    assert (
        push_secret["spec"]["selector"]["secret"]["name"] == "docdb-connection"
    )


def test_irsa_mode_skips_password_generator(helm_runner) -> None:
    rendered = render_chart(helm_runner, CHART, values={"auth.mode": "irsa"})
    manifests = load_manifests(rendered)
    secret = get_manifest(manifests, "Secret")

    assert all(m.get("kind") != "Password" for m in manifests)
    assert secret["stringData"]["PASSWORD"] == ""


def test_reflector_annotations_render(helm_runner) -> None:
    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "reflector.enabled": True,
            "reflector.pushNamespaces": ["ns-a"],
            "reflector.allowedNamespaces": ["ns-b"],
        },
    )
    secret = get_manifest(load_manifests(rendered), "Secret")

    assert (
        secret["metadata"]["annotations"][
            "reflector.v1.k8s.emberstack.com/reflection-auto-namespaces"
        ]
        == "ns-a"
    )
