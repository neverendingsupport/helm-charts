#!/usr/bin/env python3
"""Verify linter_values.yaml symlinks for each chart.

For every chart in charts/ that has a Chart.yaml, this checks that:
* charts/<chart>/linter_values.yaml exists,
* it is a symlink, and
* it resolves to tests/fixtures/<chart>/minimal-values.yaml.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Validate linter_values.yaml symlinks and return 0 if all are correct."""
    repo_root = Path(__file__).resolve().parents[1]
    charts_dir = repo_root / "charts"
    fixtures_root = repo_root / "tests" / "fixtures"

    errors: list[str] = []

    for chart_dir in sorted(charts_dir.iterdir()):
        if not chart_dir.is_dir():
            continue
        if not (chart_dir / "Chart.yaml").is_file():
            continue

        chart_name = chart_dir.name
        link_path = chart_dir / "linter_values.yaml"
        expected_target = fixtures_root / chart_name / "minimal-values.yaml"

        if not link_path.exists():
            errors.append(
                f"Missing linter_values.yaml for chart '{chart_name}': "
                f"{link_path}"
            )
            continue

        if not link_path.is_symlink():
            errors.append(
                "linter_values.yaml is not a symlink for chart "
                f"'{chart_name}': {link_path}"
            )
            continue

        resolved = link_path.resolve()
        if not expected_target.is_file():
            errors.append(
                "Expected minimal-values.yaml does not exist for chart "
                f"'{chart_name}': {expected_target}"
            )
        elif resolved != expected_target:
            errors.append(
                "linter_values.yaml points at the wrong target for chart "
                f"'{chart_name}': {link_path} -> {resolved} "
                f"(expected {expected_target})"
            )

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
