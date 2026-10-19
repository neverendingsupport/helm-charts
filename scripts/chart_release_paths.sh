#!/usr/bin/env bash
# Print the repository paths whose changes release a chart, one per line.
# release.yml uses the same set for all three decisions that depend on it:
# whether a push releases the chart, how far its version moves
# (semantic-version change_path), and which commits its release notes list.
set -euo pipefail

chart="${1:?chart name required}"

echo "charts/${chart}"
case "$chart" in
  ingress-nginx)
    # The ingress-nginx release also packages the AWS Marketplace variant,
    # staged from these inputs.
    echo "marketplace/ingress-nginx"
    echo "scripts/stage_marketplace_chart.sh"
    ;;
esac
