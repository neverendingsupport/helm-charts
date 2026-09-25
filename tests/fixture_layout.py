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

The rule holds in both directions, for files and for directories. A
golden file whose ``-values.yaml`` source is missing is an orphan:
nothing renders or compares it, so it looks like coverage while silently
rotting. A fixture directory whose chart no longer exists in ``charts/``
is an orphan for the same reason: the golden tests only visit
directories that match a chart, so nothing in it is ever rendered.
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


def is_golden_file(path: Path) -> bool:
    """Return whether the path names a golden file."""

    return path.name.endswith(".golden.yaml")


def golden_for(values_file: Path) -> Path:
    """Return the golden file that belongs to a values fixture."""

    return values_file.with_suffix(".golden.yaml")


def values_for(golden_file: Path) -> Path:
    """Return the values fixture a golden file was rendered from.

    Only a golden file has a source; asking about anything else is a
    caller bug, so it raises rather than returning a plausible name.
    """

    if not is_golden_file(golden_file):
        raise ValueError(f"not a golden file: {golden_file}")
    return golden_file.with_name(
        golden_file.name.removesuffix(".golden.yaml") + ".yaml"
    )


def chart_for(fixture_dir: Path, charts_dir: Path = CHARTS_DIR) -> Path | None:
    """Return the chart directory a fixture directory belongs to, if any."""

    chart_dir = charts_dir / fixture_dir.name
    return chart_dir if (chart_dir / "Chart.yaml").is_file() else None


def _fixture_dirs(fixtures_root: Path) -> list[Path]:
    if not fixtures_root.is_dir():
        return []
    return sorted(path for path in fixtures_root.iterdir() if path.is_dir())


def iter_fixture_dirs(
    fixtures_root: Path = FIXTURES_ROOT, charts_dir: Path = CHARTS_DIR
) -> list[Path]:
    """Return fixture directories that match a chart in charts/."""

    return [
        fixture_dir
        for fixture_dir in _fixture_dirs(fixtures_root)
        if chart_for(fixture_dir, charts_dir) is not None
    ]


def iter_orphan_fixture_dirs(
    fixtures_root: Path = FIXTURES_ROOT, charts_dir: Path = CHARTS_DIR
) -> list[Path]:
    """Return fixture directories that match no chart in charts/.

    These are what a deleted or renamed chart leaves behind. The golden
    tests never visit them, so whatever they hold is dead weight.
    """

    return [
        fixture_dir
        for fixture_dir in _fixture_dirs(fixtures_root)
        if chart_for(fixture_dir, charts_dir) is None
    ]


def iter_values_fixtures(fixture_dir: Path) -> list[Path]:
    """Return the values fixtures in one fixture directory."""

    return sorted(
        path for path in fixture_dir.glob("*.yaml") if is_values_fixture(path)
    )


def iter_orphan_goldens(fixture_dir: Path) -> list[Path]:
    """Return golden files in one directory that no values fixture owns.

    A golden is orphaned when its source name is not a values fixture
    (``ingress.golden.yaml`` would pair with ``ingress.yaml``, which the
    suffix rule rejects) or when that source file does not exist.
    """

    return sorted(
        path
        for path in fixture_dir.glob("*.yaml")
        if is_golden_file(path)
        and not (
            is_values_fixture(values_for(path)) and values_for(path).is_file()
        )
    )


__all__ = [
    "CHARTS_DIR",
    "FIXTURES_ROOT",
    "GOLDEN_SUFFIX",
    "REPO_ROOT",
    "VALUES_SUFFIX",
    "chart_for",
    "golden_for",
    "is_golden_file",
    "is_values_fixture",
    "iter_fixture_dirs",
    "iter_orphan_fixture_dirs",
    "iter_orphan_goldens",
    "iter_values_fixtures",
    "values_for",
]
