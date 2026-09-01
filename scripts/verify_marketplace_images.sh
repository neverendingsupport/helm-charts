#!/usr/bin/env bash
# Verify every image referenced by a staged Marketplace chart exists and has
# only scannable platform manifests. Run after authenticating to Marketplace
# ECR and before pushing the immutable chart version.
set -euo pipefail

CHART_DIR="${1:?staged chart directory required}"
VALUES="${CHART_DIR}/values.yaml"
[[ -f "$VALUES" ]] || { echo "ERROR: ${VALUES} not found" >&2; exit 1; }

failed=0

check_image() {
  local values_path="$1"
  local require_multiarch="${2:-}"
  local registry image tag ref manifest invalid platforms

  registry="$(yq -r "${values_path}.registry // \"\"" "$VALUES")"
  image="$(yq -r "${values_path}.image // \"\"" "$VALUES")"
  tag="$(yq -r "${values_path}.tag // \"\"" "$VALUES")"
  if [[ -z "$registry" || "$registry" == "null" \
    || -z "$image" || "$image" == "null" \
    || -z "$tag" || "$tag" == "null" ]]; then
    echo "ERROR: could not resolve ${values_path} coordinates from ${VALUES}" >&2
    failed=1
    return
  fi

  ref="${registry}/${image}:${tag}"
  if ! manifest="$(docker buildx imagetools inspect --raw "$ref" 2>&1)"; then
    echo "ERROR: ${ref} is referenced by the chart but cannot be resolved:" >&2
    echo "  ${manifest}" >&2
    failed=1
    return
  fi

  if ! invalid="$(jq -r '[.manifests[]?
      | select(((.platform.os // "unknown") == "unknown")
            or ((.platform.architecture // "unknown") == "unknown"))]
      | length' <<<"$manifest")"; then
    echo "ERROR: could not parse manifest for ${ref}" >&2
    failed=1
    return
  fi
  if [[ "$invalid" != "0" ]]; then
    echo "ERROR: ${ref} contains ${invalid} unscannable manifest entries" >&2
    echo "AWS Marketplace will reject attestations or platform-less artifacts" >&2
    failed=1
    return
  fi

  if [[ -n "$require_multiarch" ]]; then
    platforms="$(jq -r '.manifests[]?
      | select((.platform.os // "unknown") != "unknown")
      | .platform.os + "/" + .platform.architecture' <<<"$manifest")"
    for required in linux/amd64 linux/arm64; do
      if ! grep -qx "$required" <<<"$platforms"; then
        echo "ERROR: ${ref} is missing required platform ${required}" >&2
        failed=1
        return
      fi
    done
  fi
  echo "OK: ${ref}"
}

check_image '.controller.image' require-multiarch
check_image '.controller.admissionWebhooks.patch.image' require-multiarch
check_image '.defaultBackend.image'

exit "$failed"
