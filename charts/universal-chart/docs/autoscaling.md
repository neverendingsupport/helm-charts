# Configure pod autoscaling

This guide helps application developers and Kubernetes operators configure
horizontal and vertical pod autoscaling with `universal-chart`. Horizontal Pod
Autoscaler (HPA) resources use the stable Kubernetes `autoscaling/v2` API.
Vertical Pod Autoscaler (VPA) resources use the separately installed
`autoscaling.k8s.io/v1` custom resource.

## Choose an autoscaling mode

The following table summarizes the supported operating modes.

| Goal | HPA | VPA update mode | Use when |
| --- | --- | --- | --- |
| Fixed capacity | Disabled | Disabled | Replica and resource requirements are known and stable. |
| Scale replica count | Enabled | Disabled or `Off` | Load changes horizontally and resource requests are already suitable. |
| Collect resource recommendations | Optional | `Off` | You want sizing data without changing pods. |
| Apply resource recommendations | Disabled | `Initial`, `Recreate`, or `InPlaceOrRecreate` | Resource requests need automated adjustment. |
| Scale replicas and resources | Enabled | Active | HPA uses External, Object, Pods, or raw-value metrics that do not depend on VPA-managed utilization ratios. |

The chart rejects an active VPA when an HPA Resource or ContainerResource
metric uses `Utilization` for the same VPA-controlled resource. VPA changes the
request that forms the denominator of utilization, so the two controllers
would otherwise influence each other.

## Check cluster prerequisites

HPA is built into Kubernetes, but its metric APIs are separate:

- Resource and ContainerResource utilization normally require Metrics Server
  to provide `metrics.k8s.io`.
- Object and Pods metrics require a custom metrics adapter that provides
  `custom.metrics.k8s.io`.
- External metrics require an adapter that provides
  `external.metrics.k8s.io`.
- Every container included in a Resource utilization metric must declare the
  corresponding resource request. A metric supplied through
  `horizontal.metrics` fails rendering when the primary container has no
  matching request; a metric inherited from the legacy targets renders without
  one, so audit those releases with `kubectl describe hpa`. Injected sidecars
  remain the operator's responsibility in both cases.

VPA requires the VPA custom resource definitions, recommender, admission
controller, and updater to be installed by the platform team. This chart
creates a VPA resource but does not install those cluster components.

Run these read-only checks from any directory with `kubectl` configured for the
target cluster:

```bash
kubectl api-resources --api-group=autoscaling
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes
kubectl api-resources --api-group=autoscaling.k8s.io
kubectl get deployments --all-namespaces \
  -l app.kubernetes.io/name=vpa-recommender
```

The first command should list `horizontalpodautoscalers` in
`autoscaling/v2`. The second should return node metrics when Metrics Server is
available. The last two should list `verticalpodautoscalers` and the installed
VPA recommender. Installation labels vary; if the final command returns no
objects, ask the platform team for the VPA component namespace and labels.

## Configure a CPU HPA

Add the following complete minimal values to a new application, or merge the
`resources` and `autoscaling` sections into existing values:

```yaml
image:
  repository: ghcr.io/example/app
  tag: "1.2.3"

resources:
  requests:
    cpu: 100m
    memory: 128Mi

autoscaling:
  horizontal:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    metrics:
      - type: Resource
        resource:
          name: cpu
          target:
            type: Utilization
            averageUtilization: 80
```

`horizontal.metrics` accepts the native `autoscaling/v2` MetricSpec shapes:
Resource, ContainerResource, External, Object, and Pods. Kubernetes calculates
the desired replica count for every configured metric and uses the highest
result.

To set scale-up and scale-down behavior, use the native v2 behavior shape:

```yaml
autoscaling:
  horizontal:
    behavior:
      scaleUp:
        stabilizationWindowSeconds: 0
        selectPolicy: Max
        policies:
          - type: Percent
            value: 100
            periodSeconds: 60
      scaleDown:
        stabilizationWindowSeconds: 300
        selectPolicy: Min
        policies:
          - type: Percent
            value: 25
            periodSeconds: 60
```

The optional `tolerance` field requires Kubernetes support for the
`HPAConfigurableTolerance` feature. Omit it unless the platform team confirms
that the target cluster enables the feature.

## Scale from a Prometheus metric

The chart can generate both a Prometheus recording rule and its matching HPA
External metric:

```yaml
image:
  repository: ghcr.io/example/app
  tag: "1.2.3"

prometheusRule:
  additionalLabels:
    release: kube-prometheus-stack

autoscaling:
  horizontal:
    enabled: true
    minReplicas: 2
    maxReplicas: 20
    metrics: []
    prometheusScalingRules:
      - name: example_queue_messages_ready
        expr: |
          sum(
            example_queue_messages_ready{namespace="example"}
          )
        selector:
          queue: default
        target:
          type: AverageValue
          averageValue: "100"
```

The rule is labeled `hpa_metric: "true"`. A working configuration has this data
path:

1. The application exposes the source metric.
2. Prometheus scrapes the metric and evaluates the generated recording rule.
3. Prometheus Adapter discovers the `hpa_metric: "true"` series and publishes
   it through `external.metrics.k8s.io`.
4. The HPA controller reads the External metric and changes Deployment
   replicas.

The `prometheusRule.additionalLabels` values must match the Prometheus
Operator's rule selector. The adapter must be configured to discover the
`hpa_metric: "true"` label; this chart does not configure the adapter.

Before rollout, set the shell variables to the release namespace and metric
name, then verify every dependency:

```bash
NAMESPACE=example
METRIC_NAME=example_queue_messages_ready

kubectl api-resources --api-group=monitoring.coreos.com
kubectl get prometheusrules -n "${NAMESPACE}"
kubectl get --raw /apis/external.metrics.k8s.io/v1beta1
kubectl get --raw \
  "/apis/external.metrics.k8s.io/v1beta1/namespaces/${NAMESPACE}/${METRIC_NAME}"
```

Prometheus Operator discovery and adapter relist intervals can delay a new
metric. If the last command returns `NotFound`, verify the recording series and
adapter configuration before changing the HPA target.

## Start VPA in recommendation-only mode

Recommendation mode is the default adoption path. It does not change pod
resources:

```yaml
image:
  repository: ghcr.io/example/app
  tag: "1.2.3"

resources:
  requests:
    cpu: 100m
    memory: 128Mi

autoscaling:
  vertical:
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

The default `RequestsOnly` policy leaves limits unchanged. `RequestsAndLimits`
asks VPA to scale limits proportionally with requests; select it only after
confirming that behavior is suitable for the workload.

## Activate VPA with resource ceilings

Review recommendations across representative traffic and deployment cycles
before selecting an active mode. Every active policy requires `maxAllowed` for
each controlled resource:

```yaml
autoscaling:
  vertical:
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

- `Initial` applies recommendations only when pods are created.
- `Recreate` allows VPA to evict and recreate pods. Use a PodDisruptionBudget
  and enough replicas to tolerate eviction.
- `InPlaceOrRecreate` attempts an in-place resource update and may fall back to
  eviction. It requires compatible VPA components and the Kubernetes
  `InPlacePodVerticalScaling` feature. Confirm both with the platform team
  before rollout.

The chart does not support deprecated VPA mode `Auto` or direct `InPlace`.

## Migrate legacy HPA values

Legacy sibling keys under `autoscaling` remain supported:

```yaml
resources:
  requests:
    cpu: 100m

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
```

Migrate by expressing the metric through the stable v2 interface:

```yaml
resources:
  requests:
    cpu: 100m

autoscaling:
  horizontal:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    metrics:
      - type: Resource
        resource:
          name: cpu
          target:
            type: Utilization
            averageUtilization: 80
```

Precedence is evaluated per key:

- An explicitly supplied `autoscaling.horizontal` key replaces its legacy
  sibling.
- An omitted horizontal key inherits the legacy value.
- Explicit `metrics: []` suppresses legacy CPU and memory metrics.
- Explicit `prometheusScalingRules: []` suppresses legacy
  `hpaScalingRules`.
- Effective Prometheus rules append External metrics to `horizontal.metrics`.

This lets applications migrate one setting at a time. Remove legacy keys after
the preferred configuration is complete.

Validation is stricter on the new interface by design. Moving a CPU or memory
target into `horizontal.metrics` starts requiring the matching
`resources.requests` entry, so add the request in the same change that adopts
the metric.

## Verify the rollout

Set the namespace and autoscaler resource name, then inspect controller status.
With release name `example` and no name overrides, the default resource name is
`example-universal-chart`. Use the name shown by the rendered HPA or VPA when
the release sets `nameOverride` or `fullnameOverride`.

```bash
NAMESPACE=example
AUTOSCALER_NAME=example-universal-chart

kubectl get hpa -n "${NAMESPACE}" "${AUTOSCALER_NAME}"
kubectl describe hpa -n "${NAMESPACE}" "${AUTOSCALER_NAME}"
kubectl get vpa -n "${NAMESPACE}" "${AUTOSCALER_NAME}" -o yaml
kubectl get events -n "${NAMESPACE}" \
  --field-selector involvedObject.name="${AUTOSCALER_NAME}" \
  --sort-by=.lastTimestamp
```

A healthy HPA reports current metric values and the `AbleToScale`,
`ScalingActive`, and `ScalingLimited` conditions. A recommendation-only VPA
populates `status.recommendation.containerRecommendations` after it has enough
observations.

## Troubleshoot autoscaling

Use the following symptoms to locate the failing dependency:

| Symptom | Check |
| --- | --- |
| HPA shows `<unknown>` for CPU or memory | Confirm Metrics Server health and resource requests on every relevant container. |
| HPA reports a missing custom or external metric | Query the corresponding metrics API directly and check adapter discovery rules. |
| Prometheus-backed metric is absent | Confirm the PrometheusRule was selected, the recording series exists, and the adapter exposes `hpa_metric: "true"` series. |
| VPA has no recommendation | Confirm the recommender is running, the VPA target name is correct, and workload metrics are available. |
| VPA does not update pods | Confirm the update mode, updater and admission-controller health, policy bounds, PDB, and cluster feature gates. |
| Pods remain Pending after VPA updates | Compare recommendations and policy ceilings with node capacity, quotas, and LimitRanges. |

## Roll back

To stop horizontal scaling, set `autoscaling.horizontal.enabled: false` and set
`replicaCount` to the required fixed capacity. Verify that the Deployment
renders `spec.replicas` before applying the rollback.

To stop VPA mutation while keeping recommendations, change `updateMode` to
`"Off"`. To remove VPA entirely, set `autoscaling.vertical.enabled: false`.
Disabling or deleting VPA does not restore resource requests on existing pods.
Restore the intended Deployment resources in values and perform a controlled
rollout. The restart replaces pods and can reduce capacity during rollout.
Check the Deployment strategy, replica count, and PodDisruptionBudget before
running it.

```bash
NAMESPACE=example
DEPLOYMENT_NAME=example-universal-chart

kubectl rollout restart deployment -n "${NAMESPACE}" "${DEPLOYMENT_NAME}"
kubectl rollout status deployment -n "${NAMESPACE}" "${DEPLOYMENT_NAME}"
```

Set `DEPLOYMENT_NAME` to the rendered Deployment name when the release uses a
name override.
