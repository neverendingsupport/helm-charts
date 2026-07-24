"""Tests for the chart release workflow contract."""

from pathlib import Path
from typing import Any

import yaml


def release_steps() -> list[dict[str, Any]]:
    """Return the release job's workflow steps."""
    workflow_path = Path(".github/workflows/release.yml")
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    return workflow["jobs"]["release"]["steps"]


def test_release_workflow_uses_chart_scoped_semantic_version_action() -> None:
    """Version calculation should be delegated with chart path isolation."""
    steps = release_steps()
    version_step = next(step for step in steps if step.get("id") == "version")

    assert (
        version_step["uses"] == "PaulHatch/semantic-version"
        "@9f72830310d5ed81233b641ee59253644cd8a8fc"
    )
    inputs = version_step["with"]
    assert inputs["tag_prefix"] == "${{ matrix.chart }}-"
    assert inputs["change_path"] == "charts/${{ matrix.chart }}"
    assert inputs["major_pattern"] == "#major"
    assert inputs["minor_pattern"] == "#minor"
    assert inputs["ignore_commits_pattern"] == "#none"
    assert inputs["search_commit_body"] == "true"
    assert "enable_prerelease_mode" not in inputs


def test_release_workflow_creates_scoped_tag_directly() -> None:
    """The workflow should safely push the action's exact chart tag."""
    steps = release_steps()

    assert all(
        not str(step.get("uses", "")).startswith(
            "anothrNick/github-tag-action@"
        )
        for step in steps
    )
    tag_step = next(
        step for step in steps if step.get("name") == "Create chart tag"
    )
    assert tag_step["if"] == (
        "steps.version.outputs.changed == 'true' && "
        "steps.version.outputs.is_tagged != 'true'"
    )
    tag_environment = tag_step["env"]
    assert (
        tag_environment["RELEASE_TAG"]
        == "${{ steps.version.outputs.version_tag }}"
    )
    assert 'git tag "$RELEASE_TAG" "$GITHUB_SHA"' in tag_step["run"]
    assert 'git push origin "refs/tags/$RELEASE_TAG"' in tag_step["run"]
    assert "git tag -f" not in tag_step["run"]


def test_release_workflow_reconstructs_previous_chart_tag() -> None:
    """Release notes should remain scoped to the previous chart version."""
    steps = release_steps()
    notes_step = next(
        step for step in steps if step.get("name") == "Generate release notes"
    )

    assert (
        'previous_version="${{ steps.version.outputs.previous_version }}"'
        in notes_step["run"]
    )
    assert (
        'last_tag="${{ matrix.chart }}-$previous_version"' in notes_step["run"]
    )
    assert (
        'git rev-parse --verify --quiet "refs/tags/$last_tag"'
        in notes_step["run"]
    )


def test_manual_dispatch_does_not_advertise_unsupported_overrides() -> None:
    """The prototype should not silently ignore bump or force inputs."""
    workflow_path = Path(".github/workflows/release.yml")
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    dispatch_inputs = workflow[True]["workflow_dispatch"]["inputs"]

    assert set(dispatch_inputs) == {"chart"}


def test_release_workflow_keeps_chart_releaser_integration() -> None:
    """The calculated version should still feed chart packaging and upload."""
    steps = release_steps()
    publish_step = next(
        step
        for step in steps
        if step.get("name") == "Publish chart release and index"
    )

    assert (
        'cr upload -o "$owner" -r "$repo" -c "$GITHUB_SHA"'
        in publish_step["run"]
    )
