"""Validate the release workflow chart list matches charts/ directories."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main() -> int:
    """Compare release workflow chart options to chart directories."""
    workflow_path = Path(".github/workflows/release.yml")
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True, {}))
    inputs = triggers.get("workflow_dispatch", {}).get("inputs", {})
    chart_input = inputs.get("chart", {})
    options = chart_input.get("options", [])
    if not isinstance(options, list):
        print("release.yml chart options must be a list.", file=sys.stderr)
        return 1

    chart_dirs = sorted(
        path.name for path in Path("charts").iterdir() if path.is_dir()
    )
    options_sorted = sorted(options)

    if options_sorted != chart_dirs:
        print(
            "release.yml chart options do not match charts/ directories.",
            file=sys.stderr,
        )
        print(f"Options: {options_sorted}", file=sys.stderr)
        print(f"Charts:  {chart_dirs}", file=sys.stderr)
        missing = sorted(set(chart_dirs) - set(options_sorted))
        extra = sorted(set(options_sorted) - set(chart_dirs))
        if missing:
            print(f"Missing in options: {missing}", file=sys.stderr)
        if extra:
            print(f"Extra in options: {extra}", file=sys.stderr)
        return 1

    if options != options_sorted:
        print(
            "release.yml chart options should be sorted to match charts/",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
