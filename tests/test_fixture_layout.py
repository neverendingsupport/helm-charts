"""Unit tests for the shared fixture layout rule (no Helm required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from .fixture_layout import (
    golden_for,
    is_values_fixture,
    iter_fixture_dirs,
    iter_values_fixtures,
)
from .test_golden import discover_golden_pairs


class TestIsValuesFixture:
    """What the suffix rule accepts and rejects."""

    @pytest.mark.parametrize(
        "name",
        ["minimal-values.yaml", "sequenced-values.yaml", "a-b-c-values.yaml"],
    )
    def test_accepts_the_values_suffix(self, name: str) -> None:
        """A name ending in -values.yaml is a fixture."""
        assert is_values_fixture(Path(name))

    @pytest.mark.parametrize(
        "name",
        [
            "legacy-compat.yaml",
            "minimal-values.golden.yaml",
            "sequenced-values-v2.yaml",
            "values.yaml",
            "minimal-values.yml",
        ],
    )
    def test_rejects_everything_else(self, name: str) -> None:
        """Only the exact suffix counts, so near misses are not fixtures."""
        assert not is_values_fixture(Path(name))


class TestGoldenFor:
    """Mapping a fixture to its golden file."""

    def test_replaces_the_yaml_suffix(self) -> None:
        """The golden sits beside the fixture under the same stem."""
        values = Path("tests/fixtures/demo/minimal-values.yaml")

        assert golden_for(values).name == "minimal-values.golden.yaml"


class TestIterHelpers:
    """Directory and fixture iteration."""

    def test_iter_values_fixtures_filters_and_sorts(
        self, tmp_path: Path
    ) -> None:
        """Only values fixtures come back, in sorted order."""
        for name in (
            "b-values.yaml",
            "a-values.yaml",
            "legacy-compat.yaml",
            "a-values.golden.yaml",
        ):
            (tmp_path / name).write_text("{}\n")

        assert [p.name for p in iter_values_fixtures(tmp_path)] == [
            "a-values.yaml",
            "b-values.yaml",
        ]

    def test_iter_fixture_dirs_requires_a_matching_chart(self) -> None:
        """Every returned directory names a chart that exists."""
        for fixture_dir in iter_fixture_dirs():
            chart = fixture_dir.parents[2] / "charts" / fixture_dir.name
            assert (chart / "Chart.yaml").is_file()


class TestRuleIsShared:
    """The hook and the test suite cannot disagree about a fixture.

    These assert against the real repository, so a fixture that one caller
    would act on and the other would skip fails the suite.
    """

    def test_every_values_fixture_has_a_golden(self) -> None:
        """Mirror the check_fixture_goldens hook over the real fixtures."""
        missing = [
            str(values_file)
            for fixture_dir in iter_fixture_dirs()
            for values_file in iter_values_fixtures(fixture_dir)
            if not golden_for(values_file).is_file()
        ]

        assert not missing, f"fixtures without a golden file: {missing}"

    def test_golden_discovery_covers_every_values_fixture(self) -> None:
        """Nothing the hook demands a golden for is skipped when testing."""
        expected = {
            values_file
            for fixture_dir in iter_fixture_dirs()
            for values_file in iter_values_fixtures(fixture_dir)
        }
        discovered = {
            values_file for _, values_file, _ in discover_golden_pairs()
        }

        assert discovered == expected
