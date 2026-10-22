"""Unit tests for the shared fixture layout rule (no Helm required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from .fixture_layout import (
    chart_for,
    golden_for,
    is_golden_file,
    is_values_fixture,
    iter_fixture_dirs,
    iter_orphan_fixture_dirs,
    iter_orphan_goldens,
    iter_values_fixtures,
    values_for,
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


class TestValuesFor:
    """Mapping a golden file back to the fixture it belongs to."""

    def test_inverts_golden_for(self) -> None:
        """values_for undoes golden_for, so the pair rule is symmetric."""
        values = Path("tests/fixtures/demo/minimal-values.yaml")

        assert values_for(golden_for(values)) == values

    def test_strips_only_the_golden_suffix(self) -> None:
        """The stem survives whole, however long it is."""
        golden = Path("tests/fixtures/demo/a-b-c-values.golden.yaml")

        assert values_for(golden).name == "a-b-c-values.yaml"

    @pytest.mark.parametrize(
        "name", ["minimal-values.yaml", "legacy-compat.yaml", "golden.yaml"]
    )
    def test_rejects_anything_that_is_not_a_golden_file(
        self, name: str
    ) -> None:
        """A non-golden argument is a caller bug, not a plausible answer."""
        with pytest.raises(ValueError, match="not a golden file"):
            values_for(Path(name))

    @pytest.mark.parametrize(
        "name",
        ["minimal-values.golden.yaml", "a-b-c-values.golden.yaml"],
    )
    def test_is_golden_file_accepts_the_golden_suffix(self, name: str) -> None:
        """A name ending in .golden.yaml is a golden file."""
        assert is_golden_file(Path(name))

    @pytest.mark.parametrize(
        "name",
        ["minimal-values.yaml", "legacy-compat.yaml", "golden.yaml.bak"],
    )
    def test_is_golden_file_rejects_everything_else(self, name: str) -> None:
        """Only the exact suffix counts."""
        assert not is_golden_file(Path(name))


class TestIterHelpers:
    """Directory and fixture iteration."""

    def test_iter_orphan_goldens_finds_goldens_without_a_fixture(
        self, tmp_path: Path
    ) -> None:
        """A golden with no source, or a non-fixture source, is an orphan."""
        for name in (
            "a-values.yaml",
            "a-values.golden.yaml",
            "b-values.golden.yaml",  # no b-values.yaml
            "ingress.golden.yaml",  # ingress.yaml would not be a fixture
            "legacy-compat.yaml",
        ):
            (tmp_path / name).write_text("{}\n")

        assert [p.name for p in iter_orphan_goldens(tmp_path)] == [
            "b-values.golden.yaml",
            "ingress.golden.yaml",
        ]

    def test_iter_orphan_goldens_is_empty_when_every_golden_pairs(
        self, tmp_path: Path
    ) -> None:
        """A fully paired directory has no orphans."""
        for name in ("a-values.yaml", "a-values.golden.yaml"):
            (tmp_path / name).write_text("{}\n")

        assert iter_orphan_goldens(tmp_path) == []

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

    @staticmethod
    def _repo_with(tmp_path: Path) -> tuple[Path, Path]:
        """Lay out charts/ and tests/fixtures/ with one shared name."""
        charts = tmp_path / "charts"
        fixtures = tmp_path / "tests" / "fixtures"
        (charts / "kept").mkdir(parents=True)
        (charts / "kept" / "Chart.yaml").write_text("name: kept\n")
        (charts / "no-chart-yaml").mkdir()  # a directory is not a chart
        for name in ("kept", "deleted-chart", "no-chart-yaml"):
            (fixtures / name).mkdir(parents=True)
        (fixtures / "stray-file.yaml").write_text("{}\n")
        return fixtures, charts

    def test_chart_for_needs_a_chart_yaml(self, tmp_path: Path) -> None:
        """A same-named directory without Chart.yaml is not a chart."""
        fixtures, charts = self._repo_with(tmp_path)

        assert chart_for(fixtures / "kept", charts) == charts / "kept"
        assert chart_for(fixtures / "no-chart-yaml", charts) is None
        assert chart_for(fixtures / "deleted-chart", charts) is None

    def test_fixture_dirs_split_by_whether_the_chart_exists(
        self, tmp_path: Path
    ) -> None:
        """Matched and orphaned directories partition the fixture root."""
        fixtures, charts = self._repo_with(tmp_path)

        assert [p.name for p in iter_fixture_dirs(fixtures, charts)] == ["kept"]
        assert [p.name for p in iter_orphan_fixture_dirs(fixtures, charts)] == [
            "deleted-chart",
            "no-chart-yaml",
        ]

    def test_fixture_dir_helpers_tolerate_a_missing_root(
        self, tmp_path: Path
    ) -> None:
        """No fixtures root means no directories of either kind."""
        assert iter_fixture_dirs(tmp_path / "nope", tmp_path) == []
        assert iter_orphan_fixture_dirs(tmp_path / "nope", tmp_path) == []


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

    def test_no_golden_file_is_orphaned(self) -> None:
        """Every golden in the repo pairs with a values fixture.

        An orphan looks like coverage but is never rendered or compared,
        so it silently rots.
        """
        orphans = [
            str(golden)
            for fixture_dir in iter_fixture_dirs()
            for golden in iter_orphan_goldens(fixture_dir)
        ]

        assert not orphans, f"golden files without a fixture: {orphans}"

    def test_no_fixture_directory_is_orphaned(self) -> None:
        """Every fixture directory in the repo names a chart that exists.

        A deleted or renamed chart leaves its fixtures behind, and the
        golden tests skip a directory with no chart, so the leftovers are
        never rendered.
        """
        orphans = [str(path) for path in iter_orphan_fixture_dirs()]

        assert not orphans, f"fixture directories without a chart: {orphans}"

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
