"""Application image reference tests for universal-chart."""

from __future__ import annotations

import pytest

from .chart_test_utils import get_primary_container, render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifests

DIGEST = (
    "sha256:"
    "0123456789abcdef0123456789abcdef"
    "0123456789abcdef0123456789abcdef"
)


def _application_image(helm_runner, image: dict[str, object]) -> str:
    """Render the application container image reference."""

    container = get_primary_container(
        render_manifests(
            helm_runner,
            values={"image": image},
        )
    )
    return container["image"]


def test_tag_only_image_reference_stays_unchanged(helm_runner) -> None:
    """Keep the existing repository and tag reference."""

    image = _application_image(
        helm_runner,
        {
            "repository": "ghcr.io/example/app",
            "tag": "1.2.3",
        },
    )

    assert image == "ghcr.io/example/app:1.2.3"


def test_digest_only_image_reference(helm_runner) -> None:
    """Render an immutable reference without inventing a tag."""

    image = _application_image(
        helm_runner,
        {
            "repository": "ghcr.io/example/app",
            "tag": None,
            "digest": DIGEST,
        },
    )

    assert image == f"ghcr.io/example/app@{DIGEST}"


def test_legacy_digest_in_tag_remains_supported(helm_runner) -> None:
    """Keep existing tag-at-digest values working when digest is unset."""

    image = _application_image(
        helm_runner,
        {
            "repository": "ghcr.io/example/app",
            "tag": f"release-2026.07@{DIGEST}",
        },
    )

    assert image == f"ghcr.io/example/app:release-2026.07@{DIGEST}"


@pytest.mark.parametrize(
    "tag",
    [
        pytest.param(None, id="null-tag"),
        pytest.param("", id="empty-tag"),
    ],
)
def test_image_requires_tag_or_digest(
    helm_runner,
    tag: str | None,
) -> None:
    """Reject an image reference with no version selector."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "image": {
                    "repository": "ghcr.io/example/app",
                    "tag": tag,
                    "digest": None,
                }
            },
        )


@pytest.mark.parametrize(
    "digest",
    [
        pytest.param("0123456789abcdef", id="missing-algorithm"),
        pytest.param("sha256:0123456789abcdef", id="too-short"),
        pytest.param(f"sha256:{'A' * 64}", id="uppercase"),
        pytest.param(f"sha512:{'a' * 128}", id="unsupported-algorithm"),
    ],
)
def test_image_digest_rejects_invalid_formats(
    helm_runner,
    digest: str,
) -> None:
    """Reject values that aren't lowercase SHA-256 digests."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "image": {
                    "repository": "ghcr.io/example/app",
                    "tag": None,
                    "digest": digest,
                }
            },
        )


def test_image_digest_rejects_non_string_values(helm_runner) -> None:
    """Reject digest values with the wrong schema type."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "image": {
                    "repository": "ghcr.io/example/app",
                    "tag": None,
                    "digest": 123,
                }
            },
        )


@pytest.mark.parametrize(
    "tag",
    [
        pytest.param("release-2026.07", id="tag"),
        pytest.param(f"release-2026.07@{DIGEST}", id="legacy-tag-and-digest"),
    ],
)
def test_image_rejects_tag_and_digest(
    helm_runner,
    tag: str,
) -> None:
    """Reject ambiguous values with both version selectors."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "image": {
                    "repository": "ghcr.io/example/app",
                    "tag": tag,
                    "digest": DIGEST,
                }
            },
        )
