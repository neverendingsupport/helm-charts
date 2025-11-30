#!/usr/bin/env python3
"""Check that every *-values*.yaml fixture has a matching golden file.

For each chart in charts/, this verifies that:
* tests/fixtures/<chart>/ exists, and
* for every YAML file whose name contains '-values' and does not end
  with '.golden.yaml', there is a sibling '<name>.golden.yaml'.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Check that every *-values*.yaml fixture has a matching golden file."""
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
        fixture_dir = fixtures_root / chart_name

        if not fixture_dir.is_dir():
            errors.append(
                f"Missing fixtures directory for chart '{chart_name}': "
                f"{fixture_dir}"
            )
            continue

        for yaml_file in sorted(fixture_dir.glob("*.yaml")):
            name = yaml_file.name
            if name.endswith(".golden.yaml"):
                continue
            if "-values" not in name:
                continue

            base = yaml_file.with_suffix("")  # drop .yaml
            golden = base.with_suffix(".golden.yaml")
            if not golden.is_file():
                errors.append(
                    "Missing golden file for fixture: "
                    f"{yaml_file} (expected {golden})"
                )

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
