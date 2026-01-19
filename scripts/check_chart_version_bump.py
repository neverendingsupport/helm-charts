#!/usr/bin/env python3
"""Ensure modified charts have their versions bumped.

This script compares the chart directories in the current HEAD against a base
reference. If any files in a chart directory have changed but the chart's
``Chart.yaml`` version has not increased relative to the base revision, the
script exits with a non-zero status and reports the offending charts.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import yaml
from packaging.version import InvalidVersion, Version

DEFAULT_CHART_ROOT = "charts"
DEFAULT_FALLBACK_VERSION = "0.0.0"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for chart version validation."""
    parser = argparse.ArgumentParser(
        description=(
            "Check whether chart versions were bumped for charts modified "
            "since the given git ref."
        )
    )
    parser.add_argument(
        "base_ref",
        nargs="?",
        default="origin/main",
        help=(
            "Git ref to diff against. Defaults to origin/main when not "
            "provided."
        ),
    )
    parser.add_argument(
        "--chart-root",
        action="append",
        dest="chart_roots",
        default=None,
        help=(
            "Chart directory to scan for changes. Specify multiple times to "
            f"check more than one location. Defaults to '{DEFAULT_CHART_ROOT}'."
        ),
    )
    return parser.parse_args()


def git_diff_names(base_ref: str, chart_roots: list[Path]) -> list[Path]:
    """Return changed file paths under ``chart_roots`` from base_ref to HEAD."""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            base_ref,
            "HEAD",
            "--",
            *(root.as_posix() for root in chart_roots),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def load_chart_version_from_ref(ref: str, chart_yaml: Path) -> str | None:
    """Read a chart version from git history.

    Returns ``None`` if the file does not exist at the given ref.
    """
    git_object = f"{ref}:{chart_yaml.as_posix()}"
    result = subprocess.run(
        ["git", "show", git_object],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    data = yaml.safe_load(result.stdout) or {
        "version": DEFAULT_FALLBACK_VERSION
    }
    return data.get("version")


def load_chart_version_from_worktree(chart_yaml: Path) -> str | None:
    """Read the chart version from the working tree ``Chart.yaml`` file."""
    if not chart_yaml.exists():
        return None

    data = yaml.safe_load(chart_yaml.read_text()) or {}
    return data.get("version")


def group_changes_by_chart(
    paths: Iterable[Path], chart_roots: Iterable[Path]
) -> dict[tuple[Path, str], set[Path]]:
    """Group changed paths by chart root and chart directory name."""
    grouped: dict[tuple[Path, str], set[Path]] = {}
    for path in paths:
        for chart_root in chart_roots:
            try:
                relative = path.relative_to(chart_root)
            except ValueError:
                continue
            if not relative.parts:
                continue
            chart = relative.parts[0]
            grouped.setdefault((chart_root, chart), set()).add(relative)
            break
    return grouped


def main() -> int:
    """Validate chart version bumps for charts changed since the base ref."""
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    default_chart_roots = args.chart_roots or [DEFAULT_CHART_ROOT]
    chart_roots = [Path(root) for root in default_chart_roots]
    changed_files = git_diff_names(args.base_ref, chart_roots)

    charts_with_changes = group_changes_by_chart(changed_files, chart_roots)
    if not charts_with_changes:
        print("No chart changes detected; skipping version bump check.")
        return 0

    failures: list[str] = []

    for (chart_root, chart), files in sorted(charts_with_changes.items()):
        chart_yaml = repo_root / chart_root / chart / "Chart.yaml"
        current_version = load_chart_version_from_worktree(chart_yaml)
        base_version = load_chart_version_from_ref(args.base_ref, chart_yaml)

        if base_version is None:
            # New chart or Chart.yaml missing in base; nothing to compare.
            continue

        if current_version is None:
            failures.append(
                f"Chart '{chart}' changed but Chart.yaml has no version."
            )
            continue

        try:
            current = Version(current_version)
            base = Version(base_version)
        except InvalidVersion as exc:
            failures.append(
                f"Chart '{chart}' has an invalid version string: {exc}"
            )
            continue

        if current <= base:
            changed_list = ", ".join(
                str(chart_root / path) for path in sorted(files)
            )
            failures.append(
                f"Chart '{chart}' changed ({changed_list}) but version "
                f"was not bumped above {base_version!r} "
                f"(now {current_version!r})."
            )

    if failures:
        print("Chart version bump required for the following charts:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Chart versions have been bumped for all modified charts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
