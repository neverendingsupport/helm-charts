"""Where chart test fixtures live and what counts as one.

The pytest suite and the repo scripts both import this module, so the
fixture naming rule is written down once. When the rule lived in each
caller the copies drifted, and a file could satisfy the pre-commit hook
while the test suite ignored it.

A values fixture is a file in ``tests/fixtures/<chart>/`` whose name ends
with ``-values.yaml``. Its golden output sits beside it under the same
stem with ``.golden.yaml``. Any other YAML in a fixture directory is
supporting input rather than a fixture: ``legacy-compat.yaml`` feeds a
single test and has no golden of its own.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHARTS_DIR = REPO_ROOT / "charts"
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures"

VALUES_SUFFIX = "-values.yaml"
GOLDEN_SUFFIX = "-values.golden.yaml"


def is_values_fixture(path: Path) -> bool:
    """Return whether the path names a values fixture."""

    return path.name.endswith(VALUES_SUFFIX)


def golden_for(values_file: Path) -> Path:
    """Return the golden file that belongs to a values fixture."""

    return values_file.with_suffix(".golden.yaml")


def iter_fixture_dirs() -> list[Path]:
    """Return fixture directories that match a chart in charts/."""

    if not FIXTURES_ROOT.is_dir():
        return []
    return [
        fixture_dir
        for fixture_dir in sorted(FIXTURES_ROOT.iterdir())
        if fixture_dir.is_dir()
        and (CHARTS_DIR / fixture_dir.name / "Chart.yaml").is_file()
    ]


def iter_values_fixtures(fixture_dir: Path) -> list[Path]:
    """Return the values fixtures in one fixture directory."""

    return sorted(
        path for path in fixture_dir.glob("*.yaml") if is_values_fixture(path)
    )


__all__ = [
    "CHARTS_DIR",
    "FIXTURES_ROOT",
    "GOLDEN_SUFFIX",
    "REPO_ROOT",
    "VALUES_SUFFIX",
    "golden_for",
    "is_values_fixture",
    "iter_fixture_dirs",
    "iter_values_fixtures",
]
