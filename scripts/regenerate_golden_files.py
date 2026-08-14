#!/usr/bin/env python3
"""Regenerate golden manifests for every chart fixture directory."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.fixture_layout import (  # noqa: E402  (needs sys.path above)
    CHARTS_DIR,
    FIXTURES_ROOT,
    golden_for,
    iter_fixture_dirs,
    iter_values_fixtures,
)


def iter_fixture_values() -> list[tuple[str, Path, Path]]:
    """Yield (chart_name, chart_dir, values_file) tuples for every fixture."""

    fixtures: list[tuple[str, Path, Path]] = []
    for fixture_dir in iter_fixture_dirs():
        chart_dir = CHARTS_DIR / fixture_dir.name
        for values_file in iter_values_fixtures(fixture_dir):
            fixtures.append((fixture_dir.name, chart_dir, values_file))
    return fixtures


def regenerate_all() -> None:
    """Render every fixture values file into its golden manifest."""

    helm_binary = shutil.which("helm")
    if helm_binary is None:
        raise FileNotFoundError("Helm must be installed and available in PATH")

    fixtures = iter_fixture_values()
    if not fixtures:
        raise FileNotFoundError(
            f"No fixture values files were found in {FIXTURES_ROOT}"
        )

    for chart_name, chart_dir, values_file in fixtures:
        golden_file = golden_for(values_file)
        command = [
            helm_binary,
            "template",
            chart_name,
            str(chart_dir),
            "--values",
            str(values_file),
        ]
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            joined = " ".join(command)
            error = result.stderr.strip() or "unknown error"
            raise RuntimeError(f"{joined} failed: {error}")
        rel_path = golden_file.relative_to(REPO_ROOT)
        if golden_file.exists():
            existing_contents = golden_file.read_text()
            if existing_contents == result.stdout:
                print(f"Skipped {rel_path}: unchanged")
                continue

        golden_file.write_text(result.stdout)
        print(f"Updated {rel_path}")


if __name__ == "__main__":
    try:
        regenerate_all()
    except Exception as exc:  # pragma: no cover - invoked as a script
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
