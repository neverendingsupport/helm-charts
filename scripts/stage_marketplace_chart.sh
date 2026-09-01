#!/usr/bin/env bash
# Stage an ingress-nginx chart whose default values point exclusively at AWS
# Marketplace-managed ECR. The source chart is never modified.
set -euo pipefail

SOURCE_CHART="${1:?source chart directory required}"
OVERLAY="${2:?Marketplace values overlay required}"
STAGE_ROOT="${3:?stage root required}"
STAGED_CHART="${STAGE_ROOT}/ingress-nginx"

if [[ ! -f "${SOURCE_CHART}/Chart.yaml" || ! -f "${SOURCE_CHART}/values.yaml" ]]; then
  echo "ERROR: ${SOURCE_CHART} is not an unpacked Helm chart" >&2
  exit 1
fi

if [[ ! -f "$OVERLAY" ]]; then
  echo "ERROR: Marketplace overlay not found: ${OVERLAY}" >&2
  exit 1
fi

rm -rf "$STAGED_CHART"
mkdir -p "$STAGED_CHART"
cp -R "${SOURCE_CHART}/." "$STAGED_CHART/"

MERGED_VALUES="$(mktemp)"
trap 'rm -f "$MERGED_VALUES"' EXIT
yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
  "${SOURCE_CHART}/values.yaml" "$OVERLAY" > "$MERGED_VALUES"
mv "$MERGED_VALUES" "${STAGED_CHART}/values.yaml"

# The upstream certgen tag may already exist in immutable Marketplace ECR from
# an older byte-for-byte mirror. The Marketplace variant is rebuilt with NES
# OCI identity so scanners do not mistake the utility for the ingress
# controller; give that distinct content a deterministic, reusable tag.
CERTGEN_TAG="$(yq -r '.controller.admissionWebhooks.patch.image.tag // ""' \
  "${STAGED_CHART}/values.yaml")"
if [[ -z "$CERTGEN_TAG" || "$CERTGEN_TAG" == "null" ]]; then
  echo "ERROR: staged chart has no kube-webhook-certgen tag" >&2
  exit 1
fi
MARKETPLACE_CERTGEN_TAG="${CERTGEN_TAG}-nes"
if ! [[ "$MARKETPLACE_CERTGEN_TAG" =~ ^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$ ]]; then
  echo "ERROR: generated certgen tag is invalid: ${MARKETPLACE_CERTGEN_TAG}" >&2
  exit 1
fi
V="$MARKETPLACE_CERTGEN_TAG" yq -i \
  '.controller.admissionWebhooks.patch.image.tag = strenv(V)' \
  "${STAGED_CHART}/values.yaml"

# This development-only symlink points outside the copied chart.
rm -f "${STAGED_CHART}/linter_values.yaml"

echo "Staged Marketplace chart at ${STAGED_CHART}"
