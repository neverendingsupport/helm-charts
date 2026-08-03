"""Validation for universal-chart autoscaling documentation examples."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .fixture_layout import REPO_ROOT

DOCS = (
    REPO_ROOT / "charts" / "universal-chart" / "docs" / "autoscaling.md",
    REPO_ROOT / "charts" / "universal-chart" / "docs" / "autosizing.md",
)
README_TEMPLATE = REPO_ROOT / "charts" / "universal-chart" / "README.md.gotmpl"


def _yaml_blocks(path: Path) -> list[str]:
    """Return every fenced YAML example in a Markdown document."""

    return re.findall(r"```yaml\n(.*?)\n```", path.read_text(), re.DOTALL)


def test_autoscaling_yaml_examples_parse() -> None:
    """Keep every copyable autoscaling values example syntactically valid."""

    for path in (*DOCS, README_TEMPLATE):
        blocks = [
            block
            for block in _yaml_blocks(path)
            if "autoscaling:" in block or "autosizing:" in block
        ]
        assert blocks, f"expected YAML examples in {path}"
        for block in blocks:
            parsed = yaml.safe_load(block)
            assert isinstance(
                parsed, dict
            ), f"expected values mapping in {path}"
