"""Size guard for universal-chart test modules."""

from pathlib import Path

MAX_MODULE_LINES = 400


def test_universal_chart_modules_stay_reviewable() -> None:
    """Keep feature test modules at or below the review threshold."""

    tests_dir = Path(__file__).parent
    oversized = {
        path.name: len(path.read_text().splitlines())
        for path in tests_dir.glob("test_universal_chart*.py")
        if len(path.read_text().splitlines()) > MAX_MODULE_LINES
    }

    assert not oversized, (
        f"Universal-chart test modules exceed {MAX_MODULE_LINES} lines: "
        f"{oversized}"
    )
