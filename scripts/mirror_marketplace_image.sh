#!/usr/bin/env bash
# Mirror one chart image into Marketplace ECR without copying build
# attestations. AWS Marketplace rejects index entries whose platform is
# unknown/unknown with UnsupportedImageType.
set -euo pipefail

VALUES="${1:?values file required}"
VALUES_PATH="${2:?values path required}"
DEST_REPO="${3:?destination repository required}"
DEFAULT_REGISTRY="${4:?default source registry required}"
DEST_TAG_OVERRIDE="${5:-}"
DRY_RUN="${MIRROR_DRY_RUN:-}"

TAG_RE='^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$'

registry="$(yq -r "${VALUES_PATH}.registry // \"\"" "$VALUES")"
[[ -n "$registry" ]] || registry="$DEFAULT_REGISTRY"
image="$(yq -r "${VALUES_PATH}.image // \"\"" "$VALUES")"
tag="$(yq -r "${VALUES_PATH}.tag // \"\"" "$VALUES")"
digest="$(yq -r "${VALUES_PATH}.digest // \"\"" "$VALUES")"

if [[ -z "$image" || "$image" == "null" || -z "$tag" || "$tag" == "null" ]]; then
  echo "ERROR: could not resolve image and tag from ${VALUES_PATH} in ${VALUES}" >&2
  exit 1
fi

dest_tag="${DEST_TAG_OVERRIDE:-$tag}"
if ! [[ "$dest_tag" =~ $TAG_RE ]]; then
  echo "ERROR: destination tag is invalid: ${dest_tag}" >&2
  exit 1
fi

if [[ -n "$digest" ]]; then
  source_ref="${registry}/${image}@${digest}"
else
  source_ref="${registry}/${image}:${tag}"
fi
dest_ref="${DEST_REPO}:${dest_tag}"
echo "Mirroring ${source_ref} -> ${dest_ref}"

source_manifest="$(docker buildx imagetools inspect --raw "$source_ref")"
kind="$(jq -r 'if type == "object" and has("manifests") then "index" else "manifest" end' \
  <<<"$source_manifest")"

push_refs=("$source_ref")
wanted_digests=""
rebuilt=""

if [[ "$kind" == "index" ]]; then
  total="$(jq '.manifests | length' <<<"$source_manifest")"
  filtered="$(jq -r '.manifests[]
    | select(((.platform.os // "unknown") != "unknown")
         and ((.platform.architecture // "unknown") != "unknown"))
    | .digest + " " + .platform.os + "/" + .platform.architecture' \
    <<<"$source_manifest")"

  refs=()
  digests=()
  platforms=()
  while read -r child_digest platform; do
    [[ -n "$child_digest" ]] || continue
    refs+=("${registry}/${image}@${child_digest}")
    digests+=("$child_digest")
    platforms+=("$platform")
  done <<<"$filtered"

  if [[ ${#refs[@]} -eq 0 ]]; then
    echo "ERROR: no platform manifests remain after filtering ${source_ref}" >&2
    exit 1
  fi
  for required in linux/amd64 linux/arm64; do
    if ! printf '%s\n' "${platforms[@]}" | grep -qx "$required"; then
      echo "ERROR: ${source_ref} has no ${required} manifest after filtering" >&2
      exit 1
    fi
  done

  wanted_digests="$(printf '%s\n' "${digests[@]}" | sort)"
  if [[ ${#refs[@]} -eq "$total" ]]; then
    echo "Index is clean (${total} platform manifests); copying verbatim"
  else
    echo "Rebuilding index with ${#refs[@]} of ${total} manifests (${platforms[*]})"
    push_refs=("${refs[@]}")
    rebuilt=1
  fi
else
  echo "Single-manifest image; copying as-is"
  wanted_digests="$(docker buildx imagetools inspect \
    --format '{{.Manifest.Digest}}' "$source_ref")"
fi

if [[ -n "$DRY_RUN" ]]; then
  echo "MIRROR_DRY_RUN=1; would push ${push_refs[*]} as ${dest_ref}"
  docker buildx imagetools create --dry-run --tag "$dest_ref" "${push_refs[@]}"
  exit 0
fi

# Marketplace ECR tags are immutable. Treat an identical existing tag as an
# idempotent success and fail before pushing if it contains different data.
if existing="$(docker buildx imagetools inspect --raw "$dest_ref" 2>/dev/null)"; then
  existing_digests="$(jq -r '.manifests[]?.digest' <<<"$existing" | sort)"
  if [[ -n "$existing_digests" && "$existing_digests" == "$wanted_digests" ]] \
    || [[ -z "$rebuilt" && "$existing" == "$source_manifest" ]]; then
    echo "${dest_ref} already contains the expected image; skipping"
    exit 0
  fi
  echo "ERROR: ${dest_ref} already exists with different content" >&2
  echo "Marketplace ECR tags are immutable; publish under a fresh tag" >&2
  exit 1
fi

docker buildx imagetools create --tag "$dest_ref" "${push_refs[@]}"
