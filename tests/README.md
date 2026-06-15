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

Golden file tests are generic. `tests/test_golden.py` discovers every directory
under `tests/fixtures/` that has a matching chart in `charts/` and parametrizes
one test per `*-values.yaml` / `*-values.golden.yaml` pair. There is no
per-chart golden test module to write; a new chart with fixtures is covered
automatically.

1. Pick the chart fixture directory under `tests/fixtures/` (for example,
   `tests/fixtures/universal-chart`).
2. Create a new values file in that directory. Name it `<case>-values.yaml`;
   the `-values.yaml` suffix is what the test suite and the golden generator
   match on.
3. Run `make golden-files` from the repository root. The helper script renders
   every values file with Helm and rewrites the matching `.golden.yaml` outputs.
4. Verify the diff, then commit the updated values and golden files together.

CI exercises every discovered golden pair on each pull request.

### How golden comparison works

`assert_matches_golden` (in `tests/chart_test_utils.py`) does not compare the
rendered output to the golden file as a single ordered string. It splits both
sides into documents, keys each document by its `# Source:` template, `kind`,
and `metadata.name`, and compares documents with matching keys. As a result:

- The order in which Helm emits templates does not affect the result.
- A failure reports each missing, unexpected, or changed document by identity,
  and shows a unified diff for only the changed document instead of one diff of
  the entire file.
- Comparison stays byte-sensitive for indentation and content, but per-line
  trailing whitespace is ignored. The `trailing-whitespace` pre-commit hook
  strips trailing whitespace from golden files on disk, while some templates
  (for example the vendored ingress-nginx chart) render lines such as
  `nodeSelector: ` with a trailing space. Ignoring trailing whitespace keeps
  those charts comparable without weakening the rest of the check.

When a render produces more than one manifest of the same kind, look it up with
`get_manifest(manifests, kind, name=...)` or `manifests_by_name(manifests,
kind)`. A kind-only `get_manifest` call raises if the kind is ambiguous rather
than returning an arbitrary match.

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
