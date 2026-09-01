#!/usr/bin/env bash
# Rebuild kube-webhook-certgen from its digest-pinned upstream image while
# replacing misleading upstream OCI identity. The filesystem layers remain
# unchanged; only image configuration and labels differ.
set -euo pipefail

VALUES="${1:?source values file required}"
VALUES_PATH="${2:?values path required}"
DEST_REPO="${3:?destination repository required}"
DEFAULT_REGISTRY="${4:?default source registry required}"
DEST_TAG="${5:?destination tag required}"
DRY_RUN="${CERTGEN_DRY_RUN:-}"

TAG_RE='^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$'
if ! [[ "$DEST_TAG" =~ $TAG_RE ]]; then
  echo "ERROR: destination tag is invalid: ${DEST_TAG}" >&2
  exit 1
fi

registry="$(yq -r "${VALUES_PATH}.registry // \"\"" "$VALUES")"
[[ -n "$registry" ]] || registry="$DEFAULT_REGISTRY"
image="$(yq -r "${VALUES_PATH}.image // \"\"" "$VALUES")"
tag="$(yq -r "${VALUES_PATH}.tag // \"\"" "$VALUES")"
digest="$(yq -r "${VALUES_PATH}.digest // \"\"" "$VALUES")"

if [[ -z "$image" || "$image" == "null" || -z "$tag" || "$tag" == "null" ]]; then
  echo "ERROR: could not resolve image and tag from ${VALUES_PATH} in ${VALUES}" >&2
  exit 1
fi

if [[ -n "$digest" ]]; then
  source_ref="${registry}/${image}@${digest}"
else
  source_ref="${registry}/${image}:${tag}"
fi
dest_ref="${DEST_REPO}:${DEST_TAG}"
echo "Rebuilding ${source_ref} -> ${dest_ref} with NES image identity"

# The -nes tag is reserved for this relabeled image. Reuse an existing clean
# two-platform build rather than creating different bytes for an immutable tag
# on every chart release.
if [[ -z "$DRY_RUN" ]] && existing="$(docker buildx imagetools inspect --raw "$dest_ref" 2>/dev/null)"; then
  invalid="$(jq -r '[.manifests[]?
    | select(((.platform.os // "unknown") == "unknown")
         or ((.platform.architecture // "unknown") == "unknown"))] | length' \
    <<<"$existing")"
  platforms="$(jq -r '.manifests[]?
    | select((.platform.os // "unknown") != "unknown")
    | .platform.os + "/" + .platform.architecture' <<<"$existing")"
  identity_ok=1
  mapfile -t child_digests < <(jq -r '.manifests[]?
    | select((.platform.os // "unknown") != "unknown") | .digest' <<<"$existing")
  for child_digest in "${child_digests[@]}"; do
    if ! labels="$(docker buildx imagetools inspect \
      --format '{{json .Image.Config.Labels}}' "${DEST_REPO}@${child_digest}" 2>/dev/null)" \
      || ! jq -e --arg version "$DEST_TAG" '
        .["org.opencontainers.image.vendor"] == "HeroDevs"
        and .["org.opencontainers.image.source"] == "https://github.com/neverendingsupport/ingress-nginx-nes"
        and .["org.opencontainers.image.version"] == $version
      ' <<<"$labels" >/dev/null; then
      identity_ok=0
      break
    fi
  done
  if [[ "$invalid" == "0" ]] \
    && grep -qx 'linux/amd64' <<<"$platforms" \
    && grep -qx 'linux/arm64' <<<"$platforms" \
    && [[ "$identity_ok" == "1" ]]; then
    echo "${dest_ref} already contains a clean amd64/arm64 NES build; skipping"
    exit 0
  fi
  echo "ERROR: ${dest_ref} exists but is not a clean amd64/arm64 image" >&2
  echo "Marketplace ECR tags are immutable; choose a new deterministic tag" >&2
  exit 1
fi

if [[ -n "$DRY_RUN" ]]; then
  build_args=(--load)
else
  # shellcheck disable=SC2054 # comma belongs inside --platform's value
  build_args=(--platform linux/amd64,linux/arm64 --push)
fi

docker buildx build "${build_args[@]}" -t "$dest_ref" \
  --provenance=false --sbom=false \
  --build-arg BASE="$source_ref" \
  --label 'org.opencontainers.image.title=HeroDevs NES webhook certificate generator' \
  --label "org.opencontainers.image.description=Webhook certificate generator for HeroDevs NES (based on upstream kube-webhook-certgen ${tag})" \
  --label 'org.opencontainers.image.source=https://github.com/neverendingsupport/ingress-nginx-nes' \
  --label 'org.opencontainers.image.vendor=HeroDevs' \
  --label "org.opencontainers.image.version=${DEST_TAG}" \
  -f - . <<'EOF'
ARG BASE
FROM ${BASE}
EOF

echo "Rebuilt certgen pushed/loaded as ${dest_ref}"
