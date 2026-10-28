"""Actionable diagnostics from the fixture pairing hook."""

import importlib.util

import pytest

from tests.fixture_layout import REPO_ROOT, iter_orphan_fixture_dirs

SPEC = importlib.util.spec_from_file_location(
    "check_fixture_goldens", REPO_ROOT / "scripts/check_fixture_goldens.py"
)
assert SPEC is not None
assert SPEC.loader is not None
hook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hook)


@pytest.mark.parametrize(
    "golden_name,repair",
    [
        (
            "missing-values.golden.yaml",
            "no values fixture missing-values.yaml; "
            "delete it or add the fixture",
        ),
        (
            "ingress.golden.yaml",
            "expected a *-values.golden.yaml name; rename it and add "
            "the matching *-values.yaml fixture, or delete it",
        ),
    ],
)
def test_orphan_golden_diagnostic(
    tmp_path, monkeypatch, capsys, golden_name, repair
):
    """Recommend adding a fixture only when its name will pass the rule."""
    charts = tmp_path / "charts"
    fixtures = tmp_path / "fixtures"
    chart = charts / "example"
    fixture_dir = fixtures / "example"
    chart.mkdir(parents=True)
    fixture_dir.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("name: example\n")
    golden = fixture_dir / golden_name
    golden.write_text("{}\n")
    monkeypatch.setattr(hook, "CHARTS_DIR", charts)
    monkeypatch.setattr(hook, "FIXTURES_ROOT", fixtures)
    monkeypatch.setattr(
        hook,
        "iter_orphan_fixture_dirs",
        lambda: iter_orphan_fixture_dirs(fixtures, charts),
    )

    assert hook.main() == 1
    assert (
        capsys.readouterr().err
        == f"Orphaned golden file: {golden} ({repair})\n"
    )
