#!/usr/bin/env python3
"""Validate all MkDocs configs in this repository."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAMES = {"mkdocs.yml", "mkdocs.yaml"}
SKIP_PARTS = {".git", ".venv", "site"}


def iter_configs() -> list[Path]:
    """Return MkDocs config files that should be validated."""

    configs: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name not in CONFIG_NAMES:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        configs.append(path)
    return sorted(configs)


def main() -> int:
    """Build each MkDocs site in strict mode using a temporary site dir."""

    configs = iter_configs()
    if not configs:
        print("No MkDocs config files found.")
        return 0

    for config in configs:
        rel_config = config.relative_to(ROOT)
        print(f"Validating {rel_config}")
        with tempfile.TemporaryDirectory(prefix="mkdocs-site-") as site_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mkdocs",
                    "build",
                    "--strict",
                    "--quiet",
                    "--config-file",
                    str(config),
                    "--site-dir",
                    site_dir,
                ],
                cwd=ROOT,
                check=False,
            )
        if result.returncode != 0:
            return result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
