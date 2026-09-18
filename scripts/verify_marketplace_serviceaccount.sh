#!/usr/bin/env bash
# Verify the chart uses, but does not recreate, AWS's provisioned ServiceAccount.
set -euo pipefail

CHART_DIR="${1:?chart directory required}"
SENTINEL="awsmp-provisioned-sa"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

helm template awsmp "$CHART_DIR" \
  --set serviceAccount.create=false \
  --set "serviceAccount.name=${SENTINEL}" \
  > "$WORK/rendered.yaml"

if ! grep -qE "^[[:space:]]*serviceAccountName:[[:space:]]*${SENTINEL}$" "$WORK/rendered.yaml"; then
  echo "ERROR: no workload uses the supplied ServiceAccount '${SENTINEL}'" >&2
  exit 1
fi

if awk '
  /^---/ { kind=""; name="" }
  /^kind: ServiceAccount/ { kind="sa" }
  /^  name: / { if (kind=="sa") { sub(/^  name: /, ""); print } }
' "$WORK/rendered.yaml" | grep -qx "$SENTINEL"; then
  echo "ERROR: the chart recreates AWS's provisioned ServiceAccount" >&2
  exit 1
fi

echo "OK: chart honours the externally provisioned ServiceAccount"
