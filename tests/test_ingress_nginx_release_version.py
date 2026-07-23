"""Tests for ingress-nginx-specific chart release versioning."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "resolve_ingress_nginx_release_version.py"
)
SPEC = importlib.util.spec_from_file_location(
    "resolve_ingress_nginx_release_version", MODULE_PATH
)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

ReleaseVersionError = MODULE.ReleaseVersionError
SemVer = MODULE.SemVer
read_chart_version = MODULE.read_chart_version
resolve_release_version = MODULE.resolve_release_version


def test_allows_009_after_008() -> None:
    """Deleting the accidental 1.0.0 tag leaves the 0.0.9 path open."""
    assert resolve_release_version("0.0.9", ["0.0.8"]) == "0.0.9"


def test_rejects_009_while_100_exists() -> None:
    """The accidental 1.0.0 tag must block an older 0.0.9 release."""
    with pytest.raises(ReleaseVersionError, match="older than.*1.0.0"):
        resolve_release_version("0.0.9", ["0.0.8", "1.0.0"])


def test_rejects_duplicate_release() -> None:
    """An existing tag must not be silently reused."""
    with pytest.raises(ReleaseVersionError, match="already published"):
        resolve_release_version("1.0.0", ["0.0.8", "1.0.0"])


@pytest.mark.parametrize(
    "version",
    ["1", "1.0", "01.0.0", "1.0.0-"],
)
def test_rejects_malformed_versions(version: str) -> None:
    """Only valid SemVer values can be published."""
    with pytest.raises(ReleaseVersionError, match="semantic version"):
        resolve_release_version(version, [])


def test_rejects_placeholder_version() -> None:
    """ingress-nginx must always carry its intended published version."""
    with pytest.raises(ReleaseVersionError, match="explicit release version"):
        resolve_release_version("0.0.0-a.placeholder", [])


def test_semver_prerelease_precedence() -> None:
    """Prerelease comparison follows SemVer rather than string ordering."""
    assert SemVer("1.0.0-rc.10") > SemVer("1.0.0-rc.2")
    assert SemVer("1.0.0") > SemVer("1.0.0-rc.10")


def test_reads_quoted_chart_version(tmp_path: Path) -> None:
    """Quoted Chart.yaml versions and trailing comments are supported."""
    chart_file = tmp_path / "Chart.yaml"
    chart_file.write_text(
        'apiVersion: v2\nversion: "0.0.9" # release candidate\n',
        encoding="utf-8",
    )
    assert read_chart_version(chart_file) == "0.0.9"


def test_release_workflow_isolates_ingress_nginx() -> None:
    """Other charts must retain the existing tag-and-rewrite behavior."""
    workflow_path = Path(".github/workflows/release.yml")
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["release"]["steps"]

    tag_step = next(step for step in steps if step.get("id") == "next-tag")
    assert tag_step["if"] == "matrix.chart != 'ingress-nginx'"
    assert tag_step["uses"].startswith("anothrNick/github-tag-action@")

    version_step = next(step for step in steps if step.get("id") == "version")
    version_script = version_step["run"]
    ingress_branch, other_charts_branch = version_script.split(
        "else\n", maxsplit=1
    )
    assert "resolve_ingress_nginx_release_version.py" in ingress_branch
    assert "sed -i.bak" not in ingress_branch
    assert "steps.next-tag.outputs.new_tag" in other_charts_branch
    assert "sed -i.bak" in other_charts_branch
