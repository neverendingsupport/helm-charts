"""Unit tests for the ACK OpenSearch provider chart."""

from __future__ import annotations

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    load_manifests,
    render_chart,
)

CHART = ChartContext("ack-opensearch-provider")


def test_chart_renders_domain_with_defaults(helm_runner) -> None:
    rendered = render_chart(helm_runner, CHART)
    manifests = load_manifests(rendered)

    assert get_manifest(manifests, "Domain")
    assert get_manifest(manifests, "Secret")
    assert get_manifest(manifests, "Password")
    assert get_manifest(manifests, "ExternalSecret")


def test_domain_spec_supports_crd_fields(helm_runner) -> None:
    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "domain.spec.domainName": "prod-domain",
            "domain.spec.engineVersion": "OpenSearch_2.13",
            "domain.spec.clusterConfig": {
                "instanceType": "m6g.large.search",
                "instanceCount": 2,
            },
            "domain.spec.nodeToNodeEncryptionOptions.enabled": True,
            "domain.spec.offPeakWindowOptions": {"enabled": True},
        },
    )
    domain = get_manifest(load_manifests(rendered), "Domain")

    assert domain["spec"]["domainName"] == "prod-domain"
    assert domain["spec"]["clusterConfig"]["instanceCount"] == 2


def test_reflector_annotations_render(helm_runner) -> None:
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

    assert 'PASSWORD: ""' in rendered
    assert all(m.get("kind") != "Password" for m in manifests)
    assert (
        secret["stringData"]["AWS_ROLE_ARN"]
        == "arn:aws:iam::123456789012:role/opensearch"
    )
