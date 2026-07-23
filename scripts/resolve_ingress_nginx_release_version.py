#!/usr/bin/env python3
"""Resolve the committed ingress-nginx chart version for publication."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from functools import total_ordering
from pathlib import Path
from typing import Iterable

DEFAULT_CHART_FILE = Path("charts/ingress-nginx/Chart.yaml")
DEFAULT_TAG_PREFIX = "ingress-nginx-"
PLACEHOLDER_VERSION = "0.0.0-a.placeholder"

VERSION_LINE = re.compile(
    r"""^\s*version:\s*
        (?P<quote>["']?)
        (?P<version>[^"'#\s]+)
        (?P=quote)
        \s*(?:\#.*)?$
    """,
    re.VERBOSE,
)
SEMVER = re.compile(
    r"""^(?P<major>0|[1-9]\d*)
        \.(?P<minor>0|[1-9]\d*)
        \.(?P<patch>0|[1-9]\d*)
        (?:-(?P<prerelease>
            (?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)
            (?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*
        ))?
        (?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?
        $
    """,
    re.VERBOSE,
)


class ReleaseVersionError(ValueError):
    """Raised when ingress-nginx cannot be safely published."""


@total_ordering
class SemVer:
    """A minimal SemVer 2.0 value with precedence comparison."""

    def __init__(self, value: str) -> None:
        """Parse ``value`` as SemVer 2.0."""
        match = SEMVER.fullmatch(value)
        if match is None:
            raise ReleaseVersionError(
                f"{value!r} is not a valid semantic version"
            )

        self.value = value
        self.core = tuple(
            int(match.group(component))
            for component in ("major", "minor", "patch")
        )
        prerelease = match.group("prerelease")
        self.prerelease = (
            tuple(prerelease.split(".")) if prerelease is not None else None
        )

    def __eq__(self, other: object) -> bool:
        """Return whether two versions have equal SemVer precedence."""
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.core == other.core and self.prerelease == other.prerelease

    def __lt__(self, other: object) -> bool:
        """Return whether this version has lower SemVer precedence."""
        if not isinstance(other, SemVer):
            return NotImplemented
        if self.core != other.core:
            return self.core < other.core
        if self.prerelease is None:
            return False
        if other.prerelease is None:
            return True

        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return int(left) < int(right)
            if left_numeric != right_numeric:
                return left_numeric
            return left < right
        return len(self.prerelease) < len(other.prerelease)


def read_chart_version(chart_file: Path) -> str:
    """Read the top-level version field from a Helm Chart.yaml file."""
    for line in chart_file.read_text(encoding="utf-8").splitlines():
        match = VERSION_LINE.fullmatch(line)
        if match is not None:
            return match.group("version")
    raise ReleaseVersionError(f"{chart_file} has no readable version field")


def list_published_versions(repository: Path, tag_prefix: str) -> list[str]:
    """Return versions from all Git tags matching ``tag_prefix``."""
    result = subprocess.run(
        ["git", "tag", "--list", f"{tag_prefix}*"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        tag.removeprefix(tag_prefix)
        for tag in result.stdout.splitlines()
        if tag
    ]


def resolve_release_version(
    chart_version: str, published_versions: Iterable[str]
) -> str:
    """Validate and return the committed ingress-nginx chart version."""
    if chart_version == PLACEHOLDER_VERSION:
        raise ReleaseVersionError(
            "ingress-nginx must declare an explicit release version"
        )
    candidate = SemVer(chart_version)
    published = [SemVer(version) for version in published_versions]
    if not published:
        return chart_version

    if candidate in published:
        raise ReleaseVersionError(
            f"ingress-nginx-{chart_version} is already published"
        )

    latest = max(published)
    if candidate < latest:
        raise ReleaseVersionError(
            f"ingress-nginx-{chart_version} is older than the latest "
            f"published tag ingress-nginx-{latest.value}"
        )
    return chart_version


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate the committed ingress-nginx chart version against "
            "published chart tags."
        )
    )
    parser.add_argument(
        "chart_file",
        nargs="?",
        type=Path,
        default=DEFAULT_CHART_FILE,
    )
    parser.add_argument(
        "--tag-prefix",
        default=DEFAULT_TAG_PREFIX,
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
    )
    return parser.parse_args()


def main() -> int:
    """Validate and print the ingress-nginx version to publish."""
    args = parse_args()
    try:
        chart_version = read_chart_version(args.chart_file)
        published_versions = list_published_versions(
            args.repository, args.tag_prefix
        )
        print(resolve_release_version(chart_version, published_versions))
    except (
        OSError,
        ReleaseVersionError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"Unable to publish ingress-nginx: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
