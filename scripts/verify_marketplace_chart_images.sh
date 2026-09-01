#!/usr/bin/env bash
# Assert every image rendered by the staged chart uses one expected registry.
set -euo pipefail

CHART_DIR="${1:?chart directory required}"
EXPECTED_REGISTRY="${2:?expected registry required}"
EXPECTED_REGISTRY="${EXPECTED_REGISTRY%%/*}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Force optional workloads on so their images cannot escape validation.
helm template verify "$CHART_DIR" \
  --set defaultBackend.enabled=true \
  --set controller.admissionWebhooks.enabled=true \
  --set controller.admissionWebhooks.patch.enabled=true \
  > "$WORK/rendered.yaml"

grep -hoE '^[[:space:]]*image:[[:space:]]*\S+' "$WORK/rendered.yaml" \
  | sed -E 's/^[[:space:]]*image:[[:space:]]*//' \
  | tr -d '"' | sort -u > "$WORK/images.txt" || true

if [[ ! -s "$WORK/images.txt" ]]; then
  echo "ERROR: no image references rendered" >&2
  exit 1
fi

awk -v prefix="${EXPECTED_REGISTRY}/" 'index($0, prefix) != 1' \
  "$WORK/images.txt" > "$WORK/offenders.txt"

if [[ -s "$WORK/offenders.txt" ]]; then
  echo "ERROR: image(s) do not resolve to ${EXPECTED_REGISTRY}:" >&2
  sed 's/^/  /' "$WORK/offenders.txt" >&2
  exit 1
fi

certgen_tag="$(yq -r '.controller.admissionWebhooks.patch.image.tag // ""' \
  "$CHART_DIR/values.yaml")"
if [[ ! "$certgen_tag" =~ -nes$ ]]; then
  echo "ERROR: Marketplace certgen tag must use the scanner-safe -nes suffix" >&2
  exit 1
fi

echo "OK: every rendered image resolves to ${EXPECTED_REGISTRY}"
