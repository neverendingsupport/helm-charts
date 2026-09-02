# Configure vertical pod autosizing

This guide helps application developers and Kubernetes operators collect
resource recommendations or apply them with a VerticalPodAutoscaler (VPA).
The chart renders `autoscaling.k8s.io/v1`; the VPA components and custom
resource definitions are cluster prerequisites.

## Choose autosizing without HPA

The chart treats HPA autoscaling and VPA autosizing as mutually exclusive.
Rendering fails whenever both `autoscaling.enabled` and `autosizing.enabled`
are true, including recommendation-only VPA mode.

Move an HPA-managed application to autosizing in two reconciliations. Do not
disable HPA and create VPA in one Argo CD or Helm operation: a controller being
pruned can briefly overlap a newly applied controller.

1. Choose a fixed `replicaCount` that can carry expected traffic.
2. First set `autoscaling.enabled: false`, keep `autosizing.enabled: false`, and
   apply the fixed replica count.
3. Wait until the HPA is absent and the Deployment is Ready at the fixed count.
4. In a second change, set `autosizing.enabled: true` with `updateMode: Off` and
   collect recommendations.

This policy avoids competing controllers and makes controller ownership clear.

## Check VPA prerequisites

The platform must install the VPA custom resource definitions, recommender,
admission controller, and updater. This chart installs none of them.

Run these read-only checks from any directory with `kubectl` configured for the
target cluster:

```bash
kubectl api-resources --api-group=autoscaling.k8s.io
kubectl get deployments --all-namespaces \
  -l app.kubernetes.io/name=vpa-recommender
kubectl get deployments --all-namespaces \
  -l app.kubernetes.io/name=vpa-updater
kubectl get deployments --all-namespaces \
  -l app.kubernetes.io/name=vpa-admission-controller
```

The first command must list `verticalpodautoscalers`. Installation labels vary;
if a component query returns no objects, ask the platform team for its
namespace and labels.

## Collect recommendations without mutation

Use `Off` mode first. VPA observes the workload but does not mutate pod
resources:

```yaml
image:
  repository: ghcr.io/example/app
  tag: "1.2.3"

replicaCount: 2

autoscaling:
  enabled: false

resources:
  requests:
    cpu: 100m
    memory: 128Mi

autosizing:
  enabled: true
  updatePolicy:
    updateMode: "Off"
    minReplicas: 2
  resourcePolicy:
    containerPolicies:
      - containerName: "*"
        mode: Auto
        controlledResources:
          - cpu
          - memory
        controlledValues: RequestsOnly
        minAllowed: {}
        maxAllowed: {}
```

Collect data across representative traffic, deployments, and scheduled traffic
patterns. Short bursts may not materially move the recommendation because the
recommender uses historical observations.

Set the namespace and rendered VPA name, then inspect its status:

```bash
NAMESPACE=example
VPA_NAME=example-universal-chart

kubectl get vpa -n "${NAMESPACE}" "${VPA_NAME}" -o yaml
kubectl describe vpa -n "${NAMESPACE}" "${VPA_NAME}"
```

Recommendations appear under
`status.recommendation.containerRecommendations`. Investigate recommender
health and workload metrics if the field remains absent after representative
load.

## Activate autosizing with ceilings

Every active policy requires `maxAllowed` for each controlled resource. Review
the recommendation and confirm the ceilings fit namespace quotas, LimitRanges,
and available node capacity before changing the update mode.

```yaml
replicaCount: 2

autoscaling:
  enabled: false

autosizing:
  enabled: true
  updatePolicy:
    updateMode: Initial
    minReplicas: 2
  resourcePolicy:
    containerPolicies:
      - containerName: "*"
        mode: Auto
        controlledResources:
          - cpu
          - memory
        controlledValues: RequestsOnly
        minAllowed:
          cpu: 50m
          memory: 64Mi
        maxAllowed:
          cpu: "2"
          memory: 2Gi
```

Choose the update mode deliberately:

- `Off` records recommendations without changing pods.
- `Initial` applies recommendations only when pods are created.
- `Recreate` allows VPA to evict and recreate pods. Use a
  PodDisruptionBudget and enough replicas to tolerate eviction.
- `InPlaceOrRecreate` attempts an in-place resource update and may fall back to
  eviction. It requires Kubernetes 1.33 or newer with
  `InPlacePodVerticalScaling` enabled. VPA 1.4 requires its
  `InPlaceOrRecreate` feature gate; VPA 1.5 enables that gate by default, and
  VPA 1.7 removes it because the mode is generally available.

The chart rejects deprecated VPA mode `Auto`. It also rejects direct `InPlace`,
which is an alpha VPA 1.7 feature with a separate VPA feature gate. Use
`InPlaceOrRecreate` and plan for its documented eviction fallback.

See the upstream
[VPA in-place update requirements](https://github.com/kubernetes/autoscaler/blob/master/vertical-pod-autoscaler/docs/features.md#in-place-updates-inplaceorrecreate)
before selecting this mode.

`RequestsOnly` changes requests while preserving limits.
`RequestsAndLimits` scales limits proportionally with requests; use it only
after confirming that proportional scaling matches the workload's limit
policy.

`updatePolicy.minReplicas` is the number of live replicas required before the
VPA updater may attempt an eviction; it is not an availability guarantee. Use
a PodDisruptionBudget and monitor workload readiness to control disruption.

Helm validates quantity syntax and required active ceilings. Kubernetes and
the VPA admission webhook remain authoritative for relationships between
quantities, including `minAllowed` being no greater than `maxAllowed`. An
inverted range therefore fails during cluster admission rather than Helm
rendering.

## Stage an active rollout

1. Review recommendations from `Off` mode across representative load.
2. Set conservative `minAllowed` floors and explicit `maxAllowed` ceilings.
3. Prefer `Initial` for the first active rollout.
4. Confirm new pods receive expected requests.
5. Move to `Recreate` or `InPlaceOrRecreate` only when the application can
   tolerate their update behavior.
6. Monitor pod events, restarts, evictions, Pending pods, quotas, and node
   capacity.

For `InPlaceOrRecreate`, verify whether an update was in place or recreated the
pod:

```bash
NAMESPACE=example

kubectl get events -n "${NAMESPACE}" --sort-by=.lastTimestamp
kubectl get pods -n "${NAMESPACE}" -o wide
```

Capture the pod UIDs and restart counts before changing the VPA, then compare
them with this output. Events such as `InPlaceResizedByVPA` indicate an in-place
path; eviction or a changed pod UID indicates recreation. Do not filter events
only by the VPA name: resize and eviction events can be attached to Pods.

## Migrate draft nested values

The prerelease `autoscaling.vertical` path is intentionally unsupported. Move
the entire object without changing its contents:

```yaml
autosizing:
  enabled: true
  updatePolicy:
    updateMode: "Off"
    minReplicas: 2
```

The values schema rejects `autoscaling.vertical` so a stale experiment cannot
be silently ignored.

## Troubleshoot autosizing

| Symptom | Check |
| --- | --- |
| VPA resource is rejected | Confirm the CRD exists, quantities are valid, and every minimum is no greater than its maximum. |
| VPA has no recommendation | Confirm recommender health, the target Deployment name, and workload metric availability. |
| VPA does not update pods | Confirm the update mode, updater and admission-controller health, policy bounds, PDB, and feature gates. |
| Pods remain Pending | Compare recommendations and ceilings with node capacity, quotas, and LimitRanges. |
| `InPlaceOrRecreate` recreates pods | Confirm in-place resize support for the resource change and treat recreation as an expected fallback. |
| Helm reports mutual exclusion | Disable HPA and set a safe fixed `replicaCount` before enabling autosizing. |

## Stop or roll back autosizing

To stop mutation while preserving recommendations, change `updateMode` to
`"Off"`. To remove the VPA, set `autosizing.enabled: false`.

Disabling or deleting VPA does not restore resource requests on existing pods.
Restore the intended `resources` values and perform a controlled rollout. A
restart replaces pods and can reduce capacity, so review the Deployment
strategy, fixed replica count, and PodDisruptionBudget first.

```bash
NAMESPACE=example
DEPLOYMENT_NAME=example-universal-chart

kubectl rollout restart deployment -n "${NAMESPACE}" "${DEPLOYMENT_NAME}"
kubectl rollout status deployment -n "${NAMESPACE}" "${DEPLOYMENT_NAME}"
```

After rollback, verify the new pods carry the restored requests and that the
VPA resource is absent or remains in `Off` mode as intended.

If the rollback returns ownership to HPA, wait for the VPA resource to be
deleted before enabling `autoscaling` in a later reconciliation. This avoids a
transient controller overlap during apply and prune ordering.
