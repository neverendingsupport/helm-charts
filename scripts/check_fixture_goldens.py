#!/usr/bin/env python3
"""Check that every values fixture has a matching golden file.

The fixture naming rule lives in tests/fixture_layout.py so this hook and
the test suite agree on what counts as a fixture. For each chart in
charts/, this verifies that tests/fixtures/<chart>/ exists and that every
values fixture in it has a sibling golden file.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.fixture_layout import (  # noqa: E402  (needs sys.path above)
    CHARTS_DIR,
    FIXTURES_ROOT,
    golden_for,
    iter_values_fixtures,
)


def main() -> int:
    """Check that every values fixture has a matching golden file."""
    errors: list[str] = []

    for chart_dir in sorted(CHARTS_DIR.iterdir()):
        if not chart_dir.is_dir():
            continue
        if not (chart_dir / "Chart.yaml").is_file():
            continue

        fixture_dir = FIXTURES_ROOT / chart_dir.name

        if not fixture_dir.is_dir():
            errors.append(
                f"Missing fixtures directory for chart '{chart_dir.name}': "
                f"{fixture_dir}"
            )
            continue

        for values_file in iter_values_fixtures(fixture_dir):
            golden = golden_for(values_file)
            if not golden.is_file():
                errors.append(
                    "Missing golden file for fixture: "
                    f"{values_file} (expected {golden})"
                )

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
