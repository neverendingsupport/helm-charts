#!/usr/bin/env python3
"""Validate Backstage/TechDocs scaffolding for every chart."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = ROOT / "charts"
ROOT_CATALOG = ROOT / "catalog-info.yaml"
REQUIRED_FILES = (
    "catalog-info.yaml",
    "mkdocs.yml",
    "docs/index.md",
    "docs/reference.md",
)
EXPECTED_REFERENCE_TARGET = "../README.md"
CATALOG_TARGET_RE = re.compile(
    r"^\s*-\s+\./charts/([^/]+)/catalog-info\.yaml\s*$"
)


def chart_dirs() -> list[Path]:
    """Return chart directories that should have docs scaffolding."""

    return sorted(
        path
        for path in CHARTS_DIR.iterdir()
        if path.is_dir() and (path / "Chart.yaml").is_file()
    )


def catalog_targets() -> set[str]:
    """Return chart names listed in the root catalog Location targets."""

    targets: set[str] = set()
    for line in ROOT_CATALOG.read_text(encoding="utf-8").splitlines():
        match = CATALOG_TARGET_RE.match(line)
        if match:
            targets.add(match.group(1))
    return targets


def validate_chart(chart_dir: Path, listed_targets: set[str]) -> list[str]:
    """Validate one chart's docs scaffold."""

    chart_name = chart_dir.name
    errors: list[str] = []

    for relative_path in REQUIRED_FILES:
        if not (chart_dir / relative_path).exists():
            errors.append(
                f"Missing {relative_path} for chart '{chart_name}': "
                f"{chart_dir / relative_path}"
            )

    reference_path = chart_dir / "docs/reference.md"
    if reference_path.exists():
        if not reference_path.is_symlink():
            errors.append(
                f"docs/reference.md is not a symlink for chart '{chart_name}'"
            )
        else:
            target = reference_path.readlink().as_posix()
            if target != EXPECTED_REFERENCE_TARGET:
                errors.append(
                    "docs/reference.md points at the wrong target for chart "
                    f"'{chart_name}': expected {EXPECTED_REFERENCE_TARGET}, "
                    f"got {target}"
                )

    mkdocs_path = chart_dir / "mkdocs.yml"
    if mkdocs_path.exists():
        mkdocs_text = mkdocs_path.read_text(encoding="utf-8")
        if "Generated Reference: reference.md" not in mkdocs_text:
            errors.append(
                "mkdocs.yml is missing the Generated Reference page for chart "
                f"'{chart_name}'"
            )

    catalog_path = chart_dir / "catalog-info.yaml"
    if catalog_path.exists():
        catalog_text = catalog_path.read_text(encoding="utf-8")
        if "backstage.io/techdocs-ref: dir:." not in catalog_text:
            errors.append(
                "catalog-info.yaml is missing backstage.io/techdocs-ref for "
                f"chart '{chart_name}'"
            )

    if chart_name not in listed_targets:
        errors.append(
            f"Root catalog-info.yaml is missing ./charts/{chart_name}/"
            "catalog-info.yaml"
        )

    return errors


def main() -> int:
    """Validate the chart docs scaffold and root catalog entries."""

    listed_targets = catalog_targets()
    charts = chart_dirs()
    chart_names = {chart_dir.name for chart_dir in charts}
    errors: list[str] = []

    for chart_dir in charts:
        errors.extend(validate_chart(chart_dir, listed_targets))

    stale_targets = listed_targets - chart_names
    for chart_name in sorted(stale_targets):
        errors.append(
            f"Root catalog-info.yaml contains stale chart target: "
            f"./charts/{chart_name}/catalog-info.yaml"
        )

    if errors:
        for error in errors:
            print(error)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
