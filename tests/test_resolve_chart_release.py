"""Tests for chart-scoped release version resolution."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "resolve_chart_release.py"
)
SPEC = importlib.util.spec_from_file_location(
    "resolve_chart_release", MODULE_PATH
)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def git(repo: Path, *args: str) -> str:
    """Run Git in ``repo`` and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def commit_file(
    repo: Path, relative_path: str, content: str, message: str
) -> None:
    """Write and commit one file in a temporary repository."""
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", relative_path)
    git(repo, "commit", "-m", message)


def initialize_repo(repo: Path) -> None:
    """Initialize a temporary Git repository for history tests."""
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Chart Tests")
    git(repo, "config", "user.email", "chart-tests@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "tag.gpgsign", "false")
    git(repo, "config", "core.hooksPath", "/dev/null")


def test_bump_priority_matches_tag_action() -> None:
    """The highest-priority token should win within chart history."""
    history = "fix: one #patch\nfeat: two #minor\nbreak: three #major"

    assert MODULE.determine_bump(history, "patch") == "major"


def test_default_bump_is_used_without_token() -> None:
    """Manual/default bump behavior should remain available."""
    assert MODULE.determine_bump("fix: ordinary change", "minor") == "minor"


def test_stable_version_increment() -> None:
    """Stable versions should increment with normal SemVer behavior."""
    version = MODULE.StableVersion.parse("0.0.9")

    assert str(version.increment("patch")) == "0.0.10"
    assert str(version.increment("minor")) == "0.1.0"
    assert str(version.increment("major")) == "1.0.0"


def test_github_outputs_include_exact_chart_tag(tmp_path: Path) -> None:
    """The tag action should receive the fully resolved prefixed tag."""
    output_path = tmp_path / "github-output"
    resolution = MODULE.ReleaseResolution(
        previous_tag="ingress-nginx-0.0.8",
        bump="patch",
        version=MODULE.StableVersion.parse("0.0.9"),
    )

    MODULE.write_github_output(
        output_path,
        resolution,
        "ingress-nginx-",
    )

    assert output_path.read_text(encoding="utf-8").splitlines() == [
        "previous_tag=ingress-nginx-0.0.8",
        "bump=patch",
        "version=0.0.9",
        "tag=ingress-nginx-0.0.9",
    ]


def test_ingress_recovery_resolves_009_after_008(
    tmp_path: Path,
) -> None:
    """The intended ingress release should patch 0.0.8 to 0.0.9."""
    initialize_repo(tmp_path)
    commit_file(
        tmp_path,
        "charts/ingress-nginx/Chart.yaml",
        "version: 0.0.8\n",
        "feat(ingress-nginx): initial chart",
    )
    git(tmp_path, "tag", "ingress-nginx-0.0.8")
    commit_file(
        tmp_path,
        "charts/ingress-nginx/values.yaml",
        "controller: updated\n",
        "feat(ingress-nginx): release 0.0.9",
    )

    resolution = MODULE.resolve_release(
        Path("charts/ingress-nginx"),
        "ingress-nginx-",
        "patch",
        repo_root=tmp_path,
    )

    assert resolution.previous_tag == "ingress-nginx-0.0.8"
    assert resolution.bump == "patch"
    assert str(resolution.version) == "0.0.9"


def test_unrelated_major_does_not_bump_ingress_nginx(
    tmp_path: Path,
) -> None:
    """A major for another chart must not affect ingress-nginx."""
    initialize_repo(tmp_path)
    commit_file(
        tmp_path,
        "charts/ingress-nginx/Chart.yaml",
        "version: 0.0.9\n",
        "feat(ingress-nginx): initial chart",
    )
    commit_file(
        tmp_path,
        "charts/universal-chart/Chart.yaml",
        "version: 1.0.0\n",
        "feat(universal-chart): initial chart",
    )
    git(tmp_path, "tag", "ingress-nginx-0.0.9")

    commit_file(
        tmp_path,
        "charts/universal-chart/values.yaml",
        "metrics: private\n",
        "feat(universal-chart)!: secure metrics #major",
    )
    commit_file(
        tmp_path,
        "charts/ingress-nginx/values.yaml",
        "controller: enabled\n",
        "fix(ingress-nginx): update controller",
    )

    resolution = MODULE.resolve_release(
        Path("charts/ingress-nginx"),
        "ingress-nginx-",
        "patch",
        repo_root=tmp_path,
    )

    assert resolution.previous_tag == "ingress-nginx-0.0.9"
    assert resolution.bump == "patch"
    assert str(resolution.version) == "0.0.10"


def test_nonstable_chart_tags_are_ignored(tmp_path: Path) -> None:
    """Only stable SemVer tags should participate in release calculation."""
    initialize_repo(tmp_path)
    commit_file(
        tmp_path,
        "charts/ingress-nginx/Chart.yaml",
        "version: 0.0.9\n",
        "feat(ingress-nginx): initial chart",
    )
    git(tmp_path, "tag", "ingress-nginx-0.0.9")
    git(tmp_path, "tag", "ingress-nginx-1.0.0-rc.1")
    git(tmp_path, "tag", "ingress-nginx-not-a-version")
    commit_file(
        tmp_path,
        "charts/ingress-nginx/values.yaml",
        "controller: updated\n",
        "fix(ingress-nginx): update controller",
    )

    resolution = MODULE.resolve_release(
        Path("charts/ingress-nginx"),
        "ingress-nginx-",
        "patch",
        repo_root=tmp_path,
    )

    assert resolution.previous_tag == "ingress-nginx-0.0.9"
    assert str(resolution.version) == "0.0.10"


def test_chart_local_major_is_detected(tmp_path: Path) -> None:
    """A major token should apply when its commit affected the chart."""
    initialize_repo(tmp_path)
    commit_file(
        tmp_path,
        "charts/ingress-nginx/Chart.yaml",
        "version: 0.0.9\n",
        "feat(ingress-nginx): initial chart",
    )
    git(tmp_path, "tag", "ingress-nginx-0.0.9")
    commit_file(
        tmp_path,
        "charts/ingress-nginx/values.yaml",
        "controller: changed\n",
        "feat(ingress-nginx)!: change defaults #major",
    )

    resolution = MODULE.resolve_release(
        Path("charts/ingress-nginx"),
        "ingress-nginx-",
        "patch",
        repo_root=tmp_path,
    )

    assert resolution.bump == "major"
    assert str(resolution.version) == "1.0.0"


def test_commit_touching_two_charts_applies_to_both(
    tmp_path: Path,
) -> None:
    """A token applies to every chart path changed by the same commit."""
    initialize_repo(tmp_path)
    commit_file(
        tmp_path,
        "README.md",
        "initial\n",
        "chore: initialize repository",
    )
    git(tmp_path, "tag", "release-start")

    for chart in ("ingress-nginx", "universal-chart"):
        chart_file = tmp_path / "charts" / chart / "values.yaml"
        chart_file.parent.mkdir(parents=True, exist_ok=True)
        chart_file.write_text("changed: true\n", encoding="utf-8")
    git(tmp_path, "add", "charts")
    git(tmp_path, "commit", "-m", "feat(charts)!: shared change #major")

    for chart in ("ingress-nginx", "universal-chart"):
        resolution = MODULE.resolve_release(
            Path("charts") / chart,
            f"{chart}-",
            "patch",
            repo_root=tmp_path,
        )
        assert resolution.bump == "major"
        assert str(resolution.version) == "1.0.0"


def test_existing_tag_at_head_is_not_bumped_without_force(
    tmp_path: Path,
) -> None:
    """A rerun should retain a chart tag already attached to HEAD."""
    initialize_repo(tmp_path)
    commit_file(
        tmp_path,
        "charts/ingress-nginx/Chart.yaml",
        "version: 0.0.9\n",
        "fix(ingress-nginx): release chart",
    )
    git(tmp_path, "tag", "ingress-nginx-0.0.9")

    resolution = MODULE.resolve_release(
        Path("charts/ingress-nginx"),
        "ingress-nginx-",
        "patch",
        repo_root=tmp_path,
    )

    assert resolution.bump == "none"
    assert str(resolution.version) == "0.0.9"


def test_force_bumps_existing_tag_at_head(tmp_path: Path) -> None:
    """A forced dispatch should apply its default bump at tagged HEAD."""
    initialize_repo(tmp_path)
    commit_file(
        tmp_path,
        "charts/ingress-nginx/Chart.yaml",
        "version: 0.0.9\n",
        "fix(ingress-nginx): release chart",
    )
    git(tmp_path, "tag", "ingress-nginx-0.0.9")

    resolution = MODULE.resolve_release(
        Path("charts/ingress-nginx"),
        "ingress-nginx-",
        "patch",
        force=True,
        repo_root=tmp_path,
    )

    assert resolution.bump == "patch"
    assert str(resolution.version) == "0.0.10"


def test_release_workflow_creates_scoped_tag_directly() -> None:
    """The workflow should create the exact locally resolved chart tag."""
    workflow_path = Path(".github/workflows/release.yml")
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["release"]["steps"]

    version_step = next(step for step in steps if step.get("id") == "version")
    assert "scripts/resolve_chart_release.py" in version_step["run"]
    assert '--chart-path "charts/$CHART"' in version_step["run"]
    assert '--tag-prefix "$CHART-"' in version_step["run"]

    assert all(
        not str(step.get("uses", "")).startswith(
            "anothrNick/github-tag-action@"
        )
        for step in steps
    )
    tag_step = next(
        step for step in steps if step.get("name") == "Create chart tag"
    )
    assert tag_step["if"] == "steps.version.outputs.bump != 'none'"
    tag_environment = tag_step["env"]
    assert tag_environment["RELEASE_TAG"] == "${{ steps.version.outputs.tag }}"
    assert 'git tag "$RELEASE_TAG" "$GITHUB_SHA"' in tag_step["run"]
    assert 'git push origin "refs/tags/$RELEASE_TAG"' in tag_step["run"]
    assert "git tag -f" not in tag_step["run"]
    publish_step = next(
        step
        for step in steps
        if step.get("name") == "Publish chart release and index"
    )
    assert (
        'cr upload -o "$owner" -r "$repo" -c "$GITHUB_SHA"'
        in publish_step["run"]
    )
