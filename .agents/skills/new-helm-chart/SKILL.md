---
name: new-helm-chart
description: Create a new Helm chart in this repo following repository conventions. Use when asked to create a new chart, scaffold a new Helm chart, add a chart to helm-charts, or set up a chart with tests and Backstage docs.
---

# New Helm Chart

## Overview

Create a new chart in `charts/<chart>/` and include the full repository
scaffold in the same change: tests, linter symlink, generated docs wiring, and
Backstage/TechDocs metadata.

## Intake Questions

Ask these before editing files:

- Ask for the chart name.
- Ask what the chart deploys and whether it is app-facing, platform-facing, or
  AWS-resource-facing.
- Ask which existing chart is the closest model in this repo.
- Ask whether the chart should use placeholder release versioning
  (`0.0.0-a.placeholder`) or a normal semver version.
- Ask which team should own the chart in Backstage. If the user is unsure, use
  `group:default/infrastructure`.

## Workflow

1. Create the chart under `charts/<chart>/`.
2. Add or update `Chart.yaml`, `values.yaml`, templates, and any chart-local
   `README.md.gotmpl` needed by `helm-docs`.
3. Add the fixture scaffold under `tests/fixtures/<chart>/`, including at least
   `minimal-values.yaml`.
4. Create `charts/<chart>/linter_values.yaml` as a symlink to
   `../../tests/fixtures/<chart>/minimal-values.yaml`.
5. Add the Backstage/TechDocs scaffold in the same change:
   - `charts/<chart>/catalog-info.yaml`
   - `charts/<chart>/mkdocs.yml`
   - `charts/<chart>/docs/index.md`
   - `charts/<chart>/docs/reference.md -> ../README.md`
6. Add `./charts/<chart>/catalog-info.yaml` to the root `catalog-info.yaml`
   Location targets.
7. Run `helm-docs` so `README.md` exists and `docs/reference.md` points at real
   generated content.
8. If templates render differently than existing golden files expect, run
   the repo-root golden file regeneration script.
9. Run pre-commit and fix the underlying issue rather than weakening hooks.

## Required Output Rules

- Never leave a new chart without the test scaffold.
- Never leave a new chart without the Backstage/TechDocs scaffold.
- `docs/reference.md` must be a symlink to `../README.md`.
- `mkdocs.yml` must include `Generated Reference: reference.md`.
- `catalog-info.yaml` must include `backstage.io/techdocs-ref: dir:.`.
- The root `catalog-info.yaml` must include the chart's entity path.
- If chart contents change, bump `Chart.yaml` version unless it is
  `0.0.0-a.placeholder`.
- Adding new keys to `values.yaml` is usually a feature change and should bump
  the minor version.

## Validation

Run:

```bash
env PRE_COMMIT_HOME=/tmp/helm-charts-pre-commit pre-commit run --all-files
```

If available in the environment, also run the targeted test suite for the new
chart or the full repo tests.

## Related Files

- `AGENTS.md`
- `DEVELOPERS.md`
- `tests/README.md`
- the repo-root chart scaffold validator script
