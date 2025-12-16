# AGENTS

This repository is used with automated coding agents (e.g., GitHub Copilot,
OpenAI Codex, or other LLM-based refactoring tools). This guide explains the
conventions of this repo and how automated agents should respond to common
errors — especially those raised by the Python pre-commit checks.

## 1. Chart Fixtures and Golden Files

Helm chart tests rely on fixtures stored under:

```
tests/fixtures/<chart>/
```

Rules:

- Any file matching `*-values*.yaml` is a **values fixture**.
- Each must have a corresponding golden file:

```
*-values.golden.yaml
```

### Common Errors

The `scripts/check_fixture_goldens.py` pre-commit hook may report:

- `Missing fixtures directory for chart 'X': tests/fixtures/X`
- `Missing golden file for fixture: tests/fixtures/X/foo-values.yaml (expected tests/fixtures/X/foo-values.golden.yaml)`

### How agents should fix these

1. If the fixtures directory doesn’t exist, create:

   ```
   tests/fixtures/<chart>/
   ```

2. Add the missing `*-values.yaml`.
3. Generate the golden file with the golden-file regeneration script:

   ```
   <name>-values.yaml → <name>-values.golden.yaml
   ```

4. Ensure the filenames match exactly.

## 2. Minimal Values Files and Helm Lint

Each chart has a minimal values file used for:

- golden-file tests
- `helm lint` through the helmlint pre-commit hook

Convention:

```
tests/fixtures/<chart>/minimal-values.yaml
```

Each chart directory contains a **symlink**:

```
charts/<chart>/linter_values.yaml → ../../tests/fixtures/<chart>/minimal-values.yaml
```

### Common Errors

The `scripts/check_linter_symlinks.py` hook may report:

- `Missing linter_values.yaml for chart 'X'`
- `linter_values.yaml is not a symlink`
- `Expected minimal-values.yaml does not exist`
- `linter_values.yaml points at the wrong target`

### How agents should fix these

1. Ensure the minimal-values file exists.
2. Replace incorrect or missing symlinks:

   ```bash
   ln -sf ../../tests/fixtures/<chart>/minimal-values.yaml charts/<chart>/linter_values.yaml
   ```

3. Do **not** turn it into a real file.

## 3. Helm Repo Auto-Configuration

Charts may use dependencies that require `helm repo add`, and the test helpers
auto-detect and configure missing repos. Agents should not insert manual repo commands
unless modifying the test harness.

## 4. Golden File Test Regeneration

If templates or values change, regenerate golden files:

```
scripts/regenerate_golden_files.py
```

## 5. Pre-Commit Check Behavior

Agents should expect failures like:

- invalid symlink target
- missing golden file
- missing minimal-values file
- helm lint errors due to invalid YAML

Fix the underlying issue rather than disabling hooks.

When updating or adding pre-commit hooks with additional dependencies, the
language needs to be explicitly specified.  For example, when adding additional
dependencies to the python "black" hook, add "language: python".  This is to
enable renovate to automatically update those versions, as described in the
docs at https://docs.renovatebot.com/modules/manager/pre-commit/#additional-dependencies

## 6. General Guidelines for Automated Agents

- Always regenerate golden files when templates or values change.
- Keep fixture value files and golden files in sync.
- Ensure golden values output files reflect the current chart version; if chart
  versions are bumped without updating the corresponding goldens, the golden
  file tests will fail.
- Never replace `linter_values.yaml` symlinks with actual files.
- Maintain minimal values in `minimal-values.yaml`.
- Declare development dependencies in `pyproject.toml` under the `dev` optional
  dependency set and update related docs when the tooling changes.
- When GitHub Actions need Python packages, add them to a dependency group in
  `pyproject.toml` (for example, a `ci` group) and install that group in the
  workflow instead of installing ad-hoc packages. This keeps Renovate updates
  consistent.
- When pinning GitHub Actions with Renovate, use comment annotations that
  include the full semver release (for example, `# v6.1.0` instead of `# v6`)
  alongside the pinned SHA.
- If a chart's contents change, increment its version in the chart's `Chart.yaml`.
- Adding new keys to a chart's `values.yaml` (unless explicitly called out as a bugfix) is treated as a feature change and should bump the **minor** version rather than the patch level.
- PR reviews should flag any chart content change that does not bump the chart version.
- Install Helm so it is available on PATH and run the full test suite (e.g.
  `make test`) after making changes. Use the version pinned in `.tool-versions`
  (currently `helm 3.19.2`) so results are consistent. Tests rely on Helm being
  present and may perform network calls to chart repositories; investigate and
  report any environment-related failures encountered while installing Helm or
  running the suite (for example, proxy blocks when fetching Helm binaries).
- Before running tests, install the Python dev dependencies defined in
  `pyproject.toml` (for example: `python -m pip install -e ".[dev]"`). The
  `ssl` module is part of the Python standard library rather than a pip
  dependency; if `pip` reports that `ssl` is unavailable, install your
  platform's OpenSSL development libraries (e.g., `apt-get install -y
  libssl-dev` on Debian/Ubuntu) **before** installing or rebuilding Python.
  If you are using the system Python, reinstall it from your OS packages
  (e.g., `apt-get install --reinstall -y python3 python3-venv
  python3-openssl`) so that the shipped interpreter has SSL support compiled
  in, then retry the dependency install.
- The pre-commit command needs sqlite3. Like libssl, ensure that libsqlite3-dev
  (e.g. apt install libsqlite3-dev) is installed on the host machine before
  installing python3 via asdf.
- Keep feature branches rebased on the current `main` branch before adding new
  commits.
- Repository snapshots in this environment do not include Git remotes by
  default. If you need the latest `main` from GitHub, add the upstream remote
  (for example, `git remote add origin <url>`) and fetch before rebasing.
- When configuring `helm-docs` with a `--chart-search-root`, template path
  resolution depends on how the template argument is written:
  - Paths with a relative directory component (for example,
    `./README.md.gotmpl` or `./docs/README.md.gotmpl`) are resolved relative to
    the search directory.
  - Bare filenames (for example, `README.md.gotmpl` or `docs/README.md.gotmpl`)
    are always resolved relative to each chart directory discovered under the
    search directory, even if a search directory is not defined.
  Keep any chart-specific `README.md.gotmpl` files alongside the charts in the
  search directory and make new definitions which are of global scope in the
  chart search directory (or repository root, if the search directory is
  undefined).
