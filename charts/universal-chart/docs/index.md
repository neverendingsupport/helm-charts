# universal-chart

`universal-chart` is the default deployment path for most HeroDevs
application containers. It is designed for services that want standard
Kubernetes primitives plus a small number of opinionated platform integrations.

## Use It When

- the workload is primarily "run this container"
- ingress, env vars, secrets, metrics, and optional storage are enough
- the app does not need a deeply custom upstream chart

## Key Features

- standard Deployment and Service wiring
- ingress support, including the annotations commonly used with
  `external-dns`, `cert-manager`, and Forecastle
- AWS Secrets Manager integration through `awsEnvSecrets`
- `extraEnvVars`, `extraEnvSecrets`, and `extraEnvConfigmaps`
- `extraManifests` for app-adjacent resources such as `ExternalSecret`,
  `Database`, `DbUser`, or one-off Jobs
- optional `ServiceMonitor`, with public nginx ingress access to the metrics
  path blocked by default
- stable `autoscaling/v2` HorizontalPodAutoscaler (HPA) support for resource,
  container, object, pod, and external metrics
- recommendation-only and active VerticalPodAutoscaler (VPA) support
- optional `PodDisruptionBudget` through `podDisruptionBudget`
- optional Redis support
- optional S3 bucket creation via ACK-backed resources
- extra volumes and mounts
- spread helpers for AZ and spot-aware scheduling
- `terminationGracePeriodSeconds` for workloads that need slower shutdown

## Public Metrics Blocking

When `serviceMonitor.enabled` and nginx ingress are both enabled, the chart
renders a separate metrics-blocking Ingress by default. This also applies to
classless Ingresses served by the default ingress-nginx controller. The block
Ingress uses `nginx.ingress.kubernetes.io/denylist-source-range` for the
ServiceMonitor path, so Prometheus can keep scraping through the in-cluster
service while external requests to the public metrics route receive `403`.
If an explicit non-`nginx` ingress class is set, the chart fails to render
instead of silently leaving metrics public.
If an ingress-nginx controller uses another class name, add that name to
`serviceMonitor.blockExternalIngress.ingressClassNames`.

The chart fails to render if the primary Ingress explicitly declares the
metrics path or a metrics subpath while the block Ingress is active. Redirects
to the metrics path can stay on other primary Ingress paths; the redirected
metrics request is then handled by the block Ingress.

The chart fails by default when metrics blocking is enabled and the primary
Ingress uses nginx regex matching or `rewrite-target`. In that case,
ingress-nginx path precedence can route around a separate block Ingress. If the
app needs regex/rewrite ingress, set
`serviceMonitor.blockExternalIngress.allowRegexIngress: true`, set
`serviceMonitor.blockExternalIngress.path` to a more-specific public metrics
regex, and set `serviceMonitor.blockExternalIngress.pathType` to
`ImplementationSpecific`.

Set `serviceMonitor.blockExternalIngress.enabled: false` only for apps that
intentionally expose metrics publicly. If the public route differs from the
in-cluster scrape path, set `serviceMonitor.blockExternalIngress.path`. When
both the block path and `serviceMonitor.path` are null, the block path defaults
to `/metrics`, matching Prometheus' default scrape path.

## Recommended Ownership Split

For `argo-apps` deployments:

- keep app-owned, frequently changing values in the app repo
- keep ingress, namespace metadata, platform annotations, and stable
  environment defaults in `argo-apps`
- keep `version.yaml` in a deployment-only branch and make it the final values
  override

That gives CI a single place to update image tags without rewriting the rest of
the environment configuration.

## Notes For `version.yaml`

When the chart is used from Argo multi-source applications:

- keep the source that provides `version.yaml` as the last entry in
  `spec.sources`
- keep `$version_repo/.../version.yaml` as the last file in
  `helm.valueFiles`

Treat it as the final deploy-time override so nothing later in the stack can
silently replace image tags or release pins.

## Autoscaling

Use the [Autoscaling guide](autoscaling.md) to select and configure fixed
replicas, HPA, VPA recommendation mode, active VPA, or a compatible HPA and VPA
combination. The guide includes cluster prerequisites, copy-ready values,
verification commands, troubleshooting, migration from legacy HPA values, and
rollback procedures.

## PodDisruptionBudget

Use `podDisruptionBudget` when a multi-replica Deployment should limit voluntary
disruptions such as node drains. Set exactly one of `minAvailable` or
`maxUnavailable`; rendering fails when both or neither are set.

The chart also stops impossible budgets before they reach the cluster.
`minAvailable` cannot exceed `replicaCount`, or `autoscaling.minReplicas` when
autoscaling is enabled. A budget that allows no voluntary disruptions requires
`allowZeroDisruptions: true`, because it will block routine node drains.
Kubernetes rounds percentages up, so `minAvailable: "75%"` requires both pods
when the effective replica minimum is two.

```yaml
replicaCount: 2

podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

Or allow a percentage of pods to be unavailable during drains:

```yaml
replicaCount: 4

podDisruptionBudget:
  enabled: true
  maxUnavailable: "25%"
```

Set `allowZeroDisruptions: true` only when you mean to block every eviction:

```yaml
replicaCount: 2

podDisruptionBudget:
  enabled: true
  minAvailable: 2
  allowZeroDisruptions: true
```

## Generated Values Reference

The full values and schema-derived reference is generated by `helm-docs` into
the chart `README.md` during pre-commit and is included here in Backstage as
the local [Generated Reference](reference.md) page.
