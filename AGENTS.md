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
- If a chart's contents change, increment its version in the chart's `Chart.yaml`.
- PR reviews should flag any chart content change that does not bump the chart version.
- Install Helm so it is available on PATH and run the full test suite (e.g.
  `make test`) after making changes. Use the version pinned in `.tool-versions`
  (currently `helm 3.19.2`) so results are consistent. Tests rely on Helm being
  present and may perform network calls to chart repositories; investigate and
  report any environment-related failures encountered while installing Helm or
  running the suite (for example, proxy blocks when fetching Helm binaries).
- Before running tests, install the Python dev dependencies defined in
  `pyproject.toml` (for example: `python -m pip install -e ".[dev]"`).
- Keep feature branches rebased on the current `main` branch before adding new
  commits.
