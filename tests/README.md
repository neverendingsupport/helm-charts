# Chart tests

This directory contains the pytest suite and fixtures for Helm chart testing.

## Setting up the environment

Development dependencies are declared in `pyproject.toml` under the `dev`
extra. The quickest way to get a working environment (including `pytest`,
`pytest-helm-charts`, `flake8`, `PyYAML`, and `pre-commit`) is:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

Alternatively, `make venv` will create the same virtual environment using the
repository's default Python.

## Adding a golden file test

One module covers every chart. `tests/test_golden.py` walks `tests/fixtures/`,
matches each directory against a chart in `charts/`, and builds one test per
`*-values.yaml` and `*-values.golden.yaml` pair. You don't write a golden
module for a new chart. Add the fixtures and the suite picks them up.

1. Pick the chart's fixture directory under `tests/fixtures/`, for example
   `tests/fixtures/universal-chart`.
2. Add a values file there. Name it `<case>-values.yaml`; the test suite and
   the golden generator both match on that `-values.yaml` suffix.
3. Run `make golden-files` from the repository root. It renders every values
   file with Helm and rewrites the matching `.golden.yaml` output.
4. Check the diff, then commit the values and golden files together.

CI runs every discovered pair on each pull request.

### How golden comparison works

`assert_matches_golden` in `tests/chart_test_utils.py` doesn't compare the
rendered output and the golden file as one ordered string. It splits both into
documents and keys each one by its `# Source:` template, `kind`, and
`metadata.name`, then compares the documents whose keys match.

Two things follow. The order Helm renders templates in stops mattering. And a
failure names each missing, unexpected, or changed document and gives a unified
diff for that document alone, so you see which resource drifted instead of
reading a diff of the whole file.

Inside a document the comparison stays byte-for-byte on indentation and
content. It ignores whitespace at the end of a line, because the
`trailing-whitespace` pre-commit hook strips that from golden files on disk
while some templates still emit it — the vendored ingress-nginx chart renders
`nodeSelector: ` with a trailing space. Without that allowance those charts
could never match their goldens.

When a render produces several manifests of one kind, ask for one with
`get_manifest(manifests, kind, name=...)`, or take the whole set with
`manifests_by_name(manifests, kind)`. A kind-only `get_manifest` call raises
when the kind is ambiguous, so a test can't quietly assert against whichever
manifest happened to render first.

## Helm lint and linter values

The Helm lint checks (run via pre-commit and CI) use a
`linter_values.yaml` file in each chart directory. In this repository that
file is a symlink that points at the chart's minimal test values:

* `charts/<chart>/linter_values.yaml` →
  `tests/fixtures/<chart>/minimal-values.yaml`

The `minimal-values.yaml` file is both:

* The base values used by the golden-file tests for that chart.
* The values file passed to `helm lint` when running the helmlint
  pre-commit hook.

When you add a new chart or a new minimal fixture:

1. Create `tests/fixtures/<chart>/minimal-values.yaml` with the smallest
   configuration that still renders successfully.
2. Create a `linter_values.yaml` symlink in `charts/<chart>` that points to
   `../../tests/fixtures/<chart>/minimal-values.yaml`.
3. Add the chart Backstage/TechDocs scaffold:
   - `charts/<chart>/catalog-info.yaml`
   - `charts/<chart>/mkdocs.yml`
   - `charts/<chart>/docs/index.md`
   - `charts/<chart>/docs/reference.md -> ../README.md`
4. Add `./charts/<chart>/catalog-info.yaml` to the root `catalog-info.yaml`
   Location targets.

The local pre-commit checks will fail with a clear message if either the
`minimal-values.yaml` file or the `linter_values.yaml` symlink is missing
or misconfigured. The chart docs scaffold is also validated in pre-commit.

## Automatic Helm repo configuration

The test `helm_runner` fixture wraps the upstream `HelmRunner` to make
`make test` work on a fresh machine without any manual `helm repo add`
setup:

* Before running `helm dependency build`, the fixture inspects each chart's
  `Chart.yaml` file and looks at `dependencies[].repository`.
* Any repository URLs that are not already configured in `helm repo list`
  are automatically added with a generated name, and `helm repo update` is
  run once per test session.
* Each chart path only runs `helm dependency build` once per test session;
  subsequent renders reuse the cached build.

This means that, as long as your network can reach the chart repositories,
you can run tests on a clean environment and the dependencies will be
pulled automatically.

### Local/offline mode (`--skip-helm-network`)

For environments where you don't want tests to touch the network (for
example, when you're developing against fully vendored dependencies), you
can disable all Helm network operations:

```bash
pytest --skip-helm-network
```

In this mode the runner:

* Skips auto-configuring Helm repos (`helm repo add` / `helm repo update`).
* Skips `helm dependency build` for charts.

Rendering will still work as long as the chart dependencies are already
present locally (for example, pre-vendored into the `charts/` directory or
using a pre-configured Helm repo cache).

The repository Makefile also exposes a convenience target for this mode:

```bash
make test-local
```
