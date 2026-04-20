# Helm Charts

This repository is the shared chart catalog for the HeroDevs Kubernetes
platform. It is consumed directly from Argo CD, from `argo-apps`, and from
app-specific repositories when a chart-based deployment path is the right fit.

## What Lives Here

- `universal-chart` for most image-based services
- ACK provider charts for platform-managed AWS resources
- smaller supporting charts such as `nes-node-web`

Each chart now has its own Backstage entity so chart-specific docs can be
discovered without forcing users through one large repository-level document.
Each chart TechDocs set also mounts the chart's generated `README.md` locally,
so the `helm-docs` output stays the shared source of truth for GitHub,
Backstage, and future chart documentation consumers.

## How This Relates To `argo-apps`

Use `helm-charts` for reusable chart behavior.

Use `argo-apps` for:

- cluster-specific values
- ingress and DNS policy
- namespace metadata
- platform integrations and managed resources
- promotion between environments

That split keeps charts reusable while letting the Argo layer own
environment-specific behavior.

## Chart Guide

- `universal-chart`: default choice for app containers and most internal
  services
- `ack-documentdb-provider`: ACK-backed DocumentDB resource management
- `ack-opensearch-provider`: ACK-backed OpenSearch domain management
- `nes-node-web`: small reusable chart for Node-based web workloads

The generated chart `README.md` files remain the full values reference. The
TechDocs pages focus on when to use each chart and how they fit into the wider
platform.
