#!/usr/bin/env python3
"""Resolve a Helm chart release from chart-scoped Git history."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

BUMP_PRIORITY = ("major", "minor", "patch", "none")
INITIAL_VERSION = "0.0.0"


def determine_bump(history: str, default_bump: str) -> str:
    """Return the highest-priority bump token present in ``history``."""
    if default_bump not in BUMP_PRIORITY:
        raise ValueError(f"Unsupported default bump: {default_bump}")

    for bump in BUMP_PRIORITY:
        if f"#{bump}" in history:
            return bump

    return default_bump


@dataclass(frozen=True, order=True)
class StableVersion:
    """A stable three-component semantic version."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> StableVersion:
        """Parse ``value`` as a stable semantic version."""
        match = re.fullmatch(
            r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)",
            value,
        )
        if match is None:
            raise ValueError(f"Invalid stable semantic version: {value!r}")
        return cls(*(int(component) for component in match.groups()))

    def increment(self, bump: str) -> StableVersion:
        """Return this version incremented by ``bump``."""
        if bump == "major":
            return StableVersion(self.major + 1, 0, 0)
        if bump == "minor":
            return StableVersion(self.major, self.minor + 1, 0)
        if bump == "patch":
            return StableVersion(self.major, self.minor, self.patch + 1)
        if bump == "none":
            return self
        raise ValueError(f"Unsupported bump: {bump}")

    def __str__(self) -> str:
        """Return the canonical semantic version string."""
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ChartTag:
    """A chart tag and its parsed semantic version."""

    name: str
    version: StableVersion


@dataclass(frozen=True)
class ReleaseResolution:
    """The versioning decision for one chart release."""

    previous_tag: str
    bump: str
    version: StableVersion


def git(
    *args: str,
    repo_root: Path | None = None,
) -> str:
    """Run Git and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def list_chart_tags(
    tag_prefix: str,
    repo_root: Path | None = None,
) -> list[ChartTag]:
    """Return stable semantic-version tags matching ``tag_prefix``."""
    tags = []
    for name in git(
        "tag",
        "--list",
        f"{tag_prefix}*",
        repo_root=repo_root,
    ).splitlines():
        try:
            version = StableVersion.parse(name.removeprefix(tag_prefix))
        except ValueError:
            continue
        tags.append(ChartTag(name=name, version=version))
    return tags


def chart_history(
    chart_path: Path,
    previous_tag: str = "",
    repo_root: Path | None = None,
) -> str:
    """Return commit messages since ``previous_tag`` for ``chart_path``."""
    revision = f"{previous_tag}..HEAD" if previous_tag else "HEAD"
    return git(
        "log",
        revision,
        "--format=%B",
        "--",
        chart_path.as_posix(),
        repo_root=repo_root,
    )


def tag_points_to_head(
    tag: str,
    repo_root: Path | None = None,
) -> bool:
    """Return whether ``tag`` and ``HEAD`` resolve to the same commit."""
    commits = git(
        "rev-parse",
        f"{tag}^{{commit}}",
        "HEAD",
        repo_root=repo_root,
    ).splitlines()
    return commits[0] == commits[1]


def resolve_release(
    chart_path: Path,
    tag_prefix: str,
    default_bump: str,
    force: bool = False,
    repo_root: Path | None = None,
) -> ReleaseResolution:
    """Resolve the next release using only the chart's commit history."""
    tags = list_chart_tags(tag_prefix, repo_root)
    previous = max(tags, key=lambda tag: tag.version) if tags else None
    previous_tag = previous.name if previous is not None else ""
    current_version = (
        previous.version
        if previous is not None
        else StableVersion.parse(INITIAL_VERSION)
    )

    if previous is not None and not force:
        if tag_points_to_head(previous.name, repo_root):
            return ReleaseResolution(previous.name, "none", current_version)

    history = chart_history(chart_path, previous_tag, repo_root)
    bump = determine_bump(history, default_bump)
    return ReleaseResolution(
        previous_tag=previous_tag,
        bump=bump,
        version=current_version.increment(bump),
    )


def write_github_output(
    output_path: Path,
    resolution: ReleaseResolution,
    tag_prefix: str,
) -> None:
    """Append release values to a GitHub Actions output file."""
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"previous_tag={resolution.previous_tag}\n")
        output.write(f"bump={resolution.bump}\n")
        output.write(f"version={resolution.version}\n")
        output.write(f"tag={tag_prefix}{resolution.version}\n")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Resolve a chart version using only commits that affected that "
            "chart."
        )
    )
    parser.add_argument(
        "--chart-path",
        type=Path,
        required=True,
        help="Path to the chart relative to the repository root.",
    )
    parser.add_argument("--tag-prefix", required=True)
    parser.add_argument(
        "--default-bump",
        choices=BUMP_PRIORITY,
        default="patch",
        help="Bump to use when the chart history contains no bump token.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bump even when the latest chart tag already points to HEAD.",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        help="GitHub Actions output file to append resolution values to.",
    )
    return parser.parse_args()


def main() -> int:
    """Resolve and print the chart-specific release version."""
    args = parse_args()
    resolution = resolve_release(
        chart_path=args.chart_path,
        tag_prefix=args.tag_prefix,
        default_bump=args.default_bump,
        force=args.force,
    )
    if args.github_output is not None:
        write_github_output(
            args.github_output,
            resolution,
            args.tag_prefix,
        )
    print(
        f"{args.tag_prefix}{resolution.version} "
        f"({resolution.bump} from "
        f"{resolution.previous_tag or INITIAL_VERSION})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
