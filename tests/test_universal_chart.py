"""Unit tests for the universal chart."""

from __future__ import annotations

import json

import pytest

from .chart_test_utils import (
    ChartContext,
    get_manifest,
    get_primary_container,
    load_manifests,
    render_chart,
)
from .conftest import HelmTemplateError

CHART = ChartContext("universal-chart")


def test_universal_chart_renders_with_required_values(helm_runner) -> None:
    """Ensure the chart renders when only the required values are set."""

    rendered = render_chart(helm_runner, CHART)
    assert "kind: Deployment" in rendered
    assert "ghcr.io/example/app:1.2.3" in rendered


def test_name_override_updates_all_references(helm_runner) -> None:
    """Ensure every manifest reflects the requested name override."""

    override = "custom-app"
    rendered = render_chart(
        helm_runner,
        CHART,
        values={"nameOverride": override},
    )
    manifests = load_manifests(rendered)
    short_name = override
    full_name = f"{CHART.release}-{override}"

    deployment = get_manifest(manifests, "Deployment")
    service = get_manifest(manifests, "Service")
    service_account = get_manifest(manifests, "ServiceAccount")

    label_targets = [
        deployment["metadata"]["labels"],
        deployment["spec"]["selector"]["matchLabels"],
        deployment["spec"]["template"]["metadata"]["labels"],
        service["metadata"]["labels"],
        service["spec"]["selector"],
        service_account["metadata"]["labels"],
    ]
    for labels in label_targets:
        assert labels["app.kubernetes.io/name"] == short_name

    assert deployment["metadata"]["name"] == full_name
    assert service["metadata"]["name"] == full_name
    assert service_account["metadata"]["name"] == full_name
    assert (
        deployment["spec"]["template"]["spec"]["serviceAccountName"]
        == full_name
    )


def test_resources_include_requests_for_cpu_and_memory(helm_runner) -> None:
    """Ensure CPU and memory requests are rendered when specified."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "resources.requests.cpu": "250m",
            "resources.requests.memory": "512Mi",
        },
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    assert container["resources"] == {
        "requests": {"cpu": "250m", "memory": "512Mi"}
    }


def test_resources_include_memory_limits(helm_runner) -> None:
    """Ensure memory limits are rendered when specified."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"resources.limits.memory": "1024Mi"},
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    assert container["resources"] == {"limits": {"memory": "1024Mi"}}


def test_resources_include_limits_and_requests(helm_runner) -> None:
    """Ensure limits and requests coexist when both are defined."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "resources.requests.cpu": "250m",
            "resources.requests.memory": "512Mi",
            "resources.limits.memory": "1024Mi",
        },
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    assert container["resources"] == {
        "requests": {"cpu": "250m", "memory": "512Mi"},
        "limits": {"memory": "1024Mi"},
    }


def test_extra_env_vars_accept_string_values(helm_runner) -> None:
    """Ensure extraEnvVars renders simple string values."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"extraEnvVars": {"SOME_VALUE": "hello world"}},
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    env = {entry["name"]: entry for entry in container["env"]}

    assert env["SOME_VALUE"] == {"name": "SOME_VALUE", "value": "hello world"}


def test_extra_env_vars_accept_field_ref_objects(helm_runner) -> None:
    """Ensure extraEnvVars renders valueFrom fieldRef entries."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "extraEnvVars": {
                "POD_NAME": {
                    "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
                }
            }
        },
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    env = {entry["name"]: entry for entry in container["env"]}

    assert env["POD_NAME"] == {
        "name": "POD_NAME",
        "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
    }


def test_extra_env_vars_accept_secret_key_refs(helm_runner) -> None:
    """Ensure extraEnvVars renders valueFrom secretKeyRef entries."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "extraEnvVars": {
                "SECRET_THING": {
                    "valueFrom": {
                        "secretKeyRef": {"name": "my-secret", "key": "password"}
                    }
                }
            }
        },
    )
    manifests = load_manifests(rendered)
    container = get_primary_container(manifests)
    env = {entry["name"]: entry for entry in container["env"]}

    assert env["SECRET_THING"] == {
        "name": "SECRET_THING",
        "valueFrom": {"secretKeyRef": {"name": "my-secret", "key": "password"}},
    }


def test_deployment_annotations_renders_correctly(helm_runner) -> None:
    """Ensure deployment annotations are rendered."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "deployment": {
                "annotations": {"reloader.stakater.com/auto": "true"}
            }
        },
    )
    manifests = load_manifests(rendered)
    deployment = get_manifest(manifests, "Deployment")
    metadata = deployment["metadata"]

    assert "annotations" in metadata
    assert metadata["annotations"].get("reloader.stakater.com/auto") == "true"


def test_service_monitor_renders_when_enabled(helm_runner) -> None:
    """Ensure a ServiceMonitor is created when enabled."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"serviceMonitor": {"enabled": True}},
    )
    manifests = load_manifests(rendered)
    service = get_manifest(manifests, "Service")
    service_monitor = get_manifest(manifests, "ServiceMonitor")

    selector_labels = service_monitor["spec"]["selector"]["matchLabels"]
    assert selector_labels == service["spec"]["selector"]

    endpoint = service_monitor["spec"]["endpoints"][0]
    assert endpoint["port"] == "http"
    assert endpoint["path"] == "/metrics"
    assert "interval" not in endpoint


def test_service_monitor_is_not_rendered_when_disabled(helm_runner) -> None:
    """Ensure the ServiceMonitor is omitted when disabled."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"serviceMonitor": {"enabled": False}},
    )
    manifests = load_manifests(rendered)

    assert all(
        manifest.get("kind") != "ServiceMonitor" for manifest in manifests
    )


def test_service_monitor_supports_custom_path_and_interval(helm_runner) -> None:
    """Ensure path and interval overrides render in the ServiceMonitor."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "serviceMonitor": {
                "enabled": True,
                "path": "/app/metrics",
                "interval": 30,
            }
        },
    )
    manifests = load_manifests(rendered)
    endpoint = get_manifest(manifests, "ServiceMonitor")["spec"]["endpoints"][0]

    assert endpoint["path"] == "/app/metrics"
    assert endpoint["interval"] == "30s"


def test_service_monitor_interval_supports_minimum_value(helm_runner) -> None:
    """Ensure the minimum interval value renders correctly."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"serviceMonitor": {"enabled": True, "interval": 1}},
    )
    manifests = load_manifests(rendered)
    endpoint = get_manifest(manifests, "ServiceMonitor")["spec"]["endpoints"][0]

    assert endpoint["interval"] == "1s"


def test_service_monitor_path_may_be_null(helm_runner) -> None:
    """Ensure the path field is omitted when explicitly set to null."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"serviceMonitor": {"enabled": True, "path": None}},
    )
    manifests = load_manifests(rendered)
    endpoint = get_manifest(manifests, "ServiceMonitor")["spec"]["endpoints"][0]

    assert "path" not in endpoint


def test_service_monitor_rejects_invalid_enabled_value(helm_runner) -> None:
    """Reject non-boolean values for the service monitor toggle."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"serviceMonitor": {"enabled": "hero"}},
        )


def test_service_monitor_interval_rejects_negative_values(helm_runner) -> None:
    """Ensure the schema rejects negative interval values."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"serviceMonitor": {"enabled": True, "interval": -5}},
        )


def test_service_monitor_interval_rejects_zero(helm_runner) -> None:
    """Ensure the schema rejects interval values below the minimum."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"serviceMonitor": {"enabled": True, "interval": 0}},
        )


def test_spread_azs_appends_topology_constraint(helm_runner) -> None:
    """Ensure enabling AZ spread adds the extra topology constraint."""

    rendered = render_chart(helm_runner, CHART, values={"spread_azs": True})
    manifests = load_manifests(rendered)
    deployment = get_manifest(manifests, "Deployment")
    constraints = deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints", []
    )

    assert any(
        constraint.get("topologyKey") == "karpenter.sh/zone"
        for constraint in constraints
    )


def test_spread_spot_appends_topology_constraint(helm_runner) -> None:
    """Ensure enabling spot spread adds the extra topology constraint."""

    rendered = render_chart(helm_runner, CHART, values={"spread_spot": True})
    manifests = load_manifests(rendered)
    deployment = get_manifest(manifests, "Deployment")
    constraints = deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints", []
    )

    assert any(
        constraint.get("topologyKey") == "karpenter.sh/capacity-type"
        for constraint in constraints
    )


def test_spread_topology_defaults_do_not_include_extra_spreads(
    helm_runner,
) -> None:
    """Ensure spread toggles default to only the configured constraints."""

    rendered = render_chart(helm_runner, CHART)
    manifests = load_manifests(rendered)
    deployment = get_manifest(manifests, "Deployment")
    constraints = deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints", []
    )

    assert all(
        constraint.get("topologyKey")
        not in {"karpenter.sh/zone", "karpenter.sh/capacity-type"}
        for constraint in constraints
    )


def test_spread_values_reject_invalid_booleans(helm_runner) -> None:
    """Invalid boolean values fail schema validation for spread options."""

    for key in ("spread_azs", "spread_spot"):
        with pytest.raises(HelmTemplateError):
            render_chart(helm_runner, CHART, values={key: "hero"})


def test_s3_bucket_renders_when_enabled(helm_runner) -> None:
    """Ensure an S3 Bucket is created when enabled."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert bucket["metadata"]["name"] == "test-bucket"
    assert bucket["spec"]["name"] == "test-bucket"
    assert bucket["apiVersion"] == "s3.services.k8s.aws/v1alpha1"
    assert bucket["kind"] == "Bucket"


def test_s3_bucket_is_not_rendered_when_disabled(helm_runner) -> None:
    """Ensure the S3 Bucket is omitted when disabled."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"s3": {"enabled": False}},
    )
    manifests = load_manifests(rendered)

    assert all(manifest.get("kind") != "Bucket" for manifest in manifests)


def test_s3_bucket_has_correct_labels(helm_runner) -> None:
    """Ensure the S3 Bucket has the correct chart labels."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")
    labels = bucket["metadata"]["labels"]

    assert labels["app.kubernetes.io/name"] == "universal-chart"
    assert labels["app.kubernetes.io/instance"] == CHART.release
    assert labels["app.kubernetes.io/managed-by"] == "Helm"
    assert "helm.sh/chart" in labels


def test_s3_bucket_encryption_defaults_to_aes256(helm_runner) -> None:
    """Ensure encryption defaults to AES256 when not specified."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    encryption = bucket["spec"]["encryption"]["rules"][0][
        "applyServerSideEncryptionByDefault"
    ]
    assert encryption["sseAlgorithm"] == "AES256"
    assert "kmsMasterKeyID" not in encryption


def test_s3_bucket_encryption_supports_kms(helm_runner) -> None:
    """Ensure KMS encryption is rendered when specified."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
                "encryption": {
                    "sseAlgorithm": "aws:kms",
                    "kmsMasterKeyID": "alias/my-key",
                },
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    encryption = bucket["spec"]["encryption"]["rules"][0][
        "applyServerSideEncryptionByDefault"
    ]
    assert encryption["sseAlgorithm"] == "aws:kms"
    assert encryption["kmsMasterKeyID"] == "alias/my-key"


def test_s3_bucket_versioning_defaults_to_suspended(helm_runner) -> None:
    """Ensure versioning defaults to Suspended when not specified."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert bucket["spec"]["versioning"]["status"] == "Suspended"


def test_s3_bucket_versioning_can_be_enabled(helm_runner) -> None:
    """Ensure versioning can be set to Enabled."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
                "versioning": "Enabled",
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert bucket["spec"]["versioning"]["status"] == "Enabled"


def test_s3_bucket_lifecycle_rules_are_rendered(helm_runner) -> None:
    """Ensure lifecycle rules are rendered when provided."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
                "lifecycle": {
                    "rules": [
                        {
                            "id": "expire-old-objects",
                            "status": "Enabled",
                            "filter": {"prefix": "logs/"},
                            "expiration": {"days": 365},
                        }
                    ]
                },
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert "lifecycle" in bucket["spec"]
    lifecycle = bucket["spec"]["lifecycle"]
    assert len(lifecycle["rules"]) == 1
    assert lifecycle["rules"][0]["id"] == "expire-old-objects"
    assert lifecycle["rules"][0]["status"] == "Enabled"
    assert lifecycle["rules"][0]["filter"]["prefix"] == "logs/"
    assert lifecycle["rules"][0]["expiration"]["days"] == 365


def test_s3_bucket_lifecycle_is_omitted_when_empty(helm_runner) -> None:
    """Ensure lifecycle section is omitted when empty."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
                "lifecycle": {},
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert "lifecycle" not in bucket["spec"]


def test_s3_bucket_cors_rules_are_rendered(helm_runner) -> None:
    """Ensure CORS rules are rendered when provided."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
                "cors": {
                    "corsRules": [
                        {
                            "id": "test-cors-rule",
                            "allowedOrigins": ["*"],
                            "allowedMethods": ["GET", "PUT"],
                            "allowedHeaders": ["*"],
                            "maxAgeSeconds": 3000,
                        }
                    ]
                },
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert "cors" in bucket["spec"]
    cors = bucket["spec"]["cors"]
    assert len(cors["corsRules"]) == 1
    assert cors["corsRules"][0]["id"] == "test-cors-rule"
    assert cors["corsRules"][0]["allowedOrigins"] == ["*"]
    assert cors["corsRules"][0]["allowedMethods"] == ["GET", "PUT"]
    assert cors["corsRules"][0]["allowedHeaders"] == ["*"]
    assert cors["corsRules"][0]["maxAgeSeconds"] == 3000


def test_s3_bucket_cors_is_omitted_when_empty(helm_runner) -> None:
    """Ensure CORS section is omitted when empty."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
                "cors": {},
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert "cors" not in bucket["spec"]


def test_s3_bucket_policy_is_rendered_as_json_string(helm_runner) -> None:
    """Ensure policy is rendered as a JSON string when provided."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
                "policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "PublicReadGetObject",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["s3:GetObject"],
                            "Resource": ["arn:aws:s3:::test-bucket/*"],
                        }
                    ],
                },
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert "policy" in bucket["spec"]
    policy_str = bucket["spec"]["policy"]
    assert isinstance(policy_str, str)

    policy_dict = json.loads(policy_str)
    assert policy_dict["Version"] == "2012-10-17"
    assert len(policy_dict["Statement"]) == 1
    assert policy_dict["Statement"][0]["Sid"] == "PublicReadGetObject"
    assert policy_dict["Statement"][0]["Effect"] == "Allow"
    assert policy_dict["Statement"][0]["Principal"] == "*"
    assert policy_dict["Statement"][0]["Action"] == ["s3:GetObject"]
    assert policy_dict["Statement"][0]["Resource"] == [
        "arn:aws:s3:::test-bucket/*"
    ]


def test_s3_bucket_policy_is_omitted_when_empty(helm_runner) -> None:
    """Ensure policy section is omitted when empty."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "s3": {
                "enabled": True,
                "s3bucketName": "test-bucket",
                "policy": {},
            }
        },
    )
    manifests = load_manifests(rendered)
    bucket = get_manifest(manifests, "Bucket")

    assert "policy" not in bucket["spec"]
