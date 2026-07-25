"""S3 Bucket tests for universal-chart."""

from __future__ import annotations

import json
from typing import Any

from .universal_chart_test_utils import CHART, render_manifest, render_manifests


def _bucket_values(**overrides: Any) -> dict[str, Any]:
    """Build enabled S3 values with a stable bucket name."""

    values: dict[str, Any] = {
        "enabled": True,
        "s3bucketName": "test-bucket",
    }
    values.update(overrides)
    return {"s3": values}


def _bucket(helm_runner, **overrides: Any) -> dict[str, Any]:
    """Render the S3 Bucket with optional value overrides."""

    return render_manifest(
        helm_runner,
        "Bucket",
        values=_bucket_values(**overrides),
    )


def test_s3_bucket_renders_when_enabled(helm_runner) -> None:
    """Create a Bucket with the requested name."""

    bucket = _bucket(helm_runner)

    assert bucket["metadata"]["name"] == "test-bucket"
    assert bucket["spec"]["name"] == "test-bucket"
    assert bucket["apiVersion"] == "s3.services.k8s.aws/v1alpha1"
    assert bucket["kind"] == "Bucket"


def test_s3_bucket_is_not_rendered_when_disabled(helm_runner) -> None:
    """Omit the Bucket when disabled."""

    manifests = render_manifests(
        helm_runner,
        values={"s3": {"enabled": False}},
    )

    assert all(item.get("kind") != "Bucket" for item in manifests)


def test_s3_bucket_has_chart_labels(helm_runner) -> None:
    """Apply the standard chart labels to the Bucket."""

    labels = _bucket(helm_runner)["metadata"]["labels"]

    assert labels["app.kubernetes.io/name"] == "universal-chart"
    assert labels["app.kubernetes.io/instance"] == CHART.release
    assert labels["app.kubernetes.io/managed-by"] == "Helm"
    assert "helm.sh/chart" in labels


def test_s3_bucket_encryption_defaults_to_aes256(helm_runner) -> None:
    """Default server-side encryption to AES256."""

    encryption = _bucket(helm_runner)["spec"]["encryption"]["rules"][0][
        "applyServerSideEncryptionByDefault"
    ]

    assert encryption["sseAlgorithm"] == "AES256"
    assert "kmsMasterKeyID" not in encryption


def test_s3_bucket_encryption_supports_kms(helm_runner) -> None:
    """Render KMS encryption when configured."""

    encryption = _bucket(
        helm_runner,
        encryption={
            "sseAlgorithm": "aws:kms",
            "kmsMasterKeyID": "alias/my-key",
        },
    )["spec"]["encryption"]["rules"][0]["applyServerSideEncryptionByDefault"]

    assert encryption["sseAlgorithm"] == "aws:kms"
    assert encryption["kmsMasterKeyID"] == "alias/my-key"


def test_s3_bucket_versioning_defaults_to_suspended(helm_runner) -> None:
    """Leave versioning suspended by default."""

    assert _bucket(helm_runner)["spec"]["versioning"]["status"] == "Suspended"


def test_s3_bucket_versioning_can_be_enabled(helm_runner) -> None:
    """Enable versioning when requested."""

    bucket = _bucket(helm_runner, versioning="Enabled")

    assert bucket["spec"]["versioning"]["status"] == "Enabled"


def test_s3_bucket_lifecycle_rules_are_rendered(helm_runner) -> None:
    """Render configured lifecycle rules."""

    lifecycle = _bucket(
        helm_runner,
        lifecycle={
            "rules": [
                {
                    "id": "expire-old-objects",
                    "status": "Enabled",
                    "filter": {"prefix": "logs/"},
                    "expiration": {"days": 365},
                }
            ]
        },
    )["spec"]["lifecycle"]

    assert lifecycle["rules"] == [
        {
            "id": "expire-old-objects",
            "status": "Enabled",
            "filter": {"prefix": "logs/"},
            "expiration": {"days": 365},
        }
    ]


def test_s3_bucket_lifecycle_is_omitted_when_empty(helm_runner) -> None:
    """Omit an empty lifecycle section."""

    assert "lifecycle" not in _bucket(helm_runner, lifecycle={})["spec"]


def test_s3_bucket_cors_rules_are_rendered(helm_runner) -> None:
    """Render configured CORS rules."""

    cors_rule = {
        "id": "test-cors-rule",
        "allowedOrigins": ["*"],
        "allowedMethods": ["GET", "PUT"],
        "allowedHeaders": ["*"],
        "maxAgeSeconds": 3000,
    }
    cors = _bucket(
        helm_runner,
        cors={"corsRules": [cors_rule]},
    )[
        "spec"
    ]["cors"]

    assert cors["corsRules"] == [cors_rule]


def test_s3_bucket_cors_is_omitted_when_empty(helm_runner) -> None:
    """Omit an empty CORS section."""

    assert "cors" not in _bucket(helm_runner, cors={})["spec"]


def test_s3_bucket_policy_is_rendered_as_json_string(helm_runner) -> None:
    """Serialize the configured policy as JSON."""

    policy = {
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
    }
    rendered_policy = _bucket(helm_runner, policy=policy)["spec"]["policy"]

    assert isinstance(rendered_policy, str)
    assert json.loads(rendered_policy) == policy


def test_s3_bucket_policy_is_omitted_when_empty(helm_runner) -> None:
    """Omit an empty policy."""

    assert "policy" not in _bucket(helm_runner, policy={})["spec"]
