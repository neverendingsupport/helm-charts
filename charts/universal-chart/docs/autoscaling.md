# Configure horizontal pod autoscaling

This guide helps application developers and Kubernetes operators configure the
chart-managed HorizontalPodAutoscaler (HPA). The chart uses the stable
Kubernetes `autoscaling/v2` API and keeps the released flat `autoscaling`
values interface.

HPA autoscaling and VPA autosizing are mutually exclusive in this chart. If
`autoscaling.enabled` and `autosizing.enabled` are both true, Helm rendering
fails. Use the [autosizing guide](autosizing.md) when resource recommendations
or vertical resource changes are the goal.

## Check metric prerequisites

HPA is built into Kubernetes, but its metric APIs are installed separately:

- Resource and ContainerResource utilization normally require Metrics Server
  to provide `metrics.k8s.io`.
- Object and Pods metrics require an adapter that provides
  `custom.metrics.k8s.io`.
- External metrics require an adapter that provides
  `external.metrics.k8s.io`.
- Every container included in a utilization calculation must declare the
  corresponding resource request.

Run these read-only checks from any directory with `kubectl` configured for the
target cluster:

```bash
kubectl api-resources --api-group=autoscaling
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes
kubectl get --raw /apis/custom.metrics.k8s.io/v1beta2
kubectl get --raw /apis/external.metrics.k8s.io/v1beta1
```

The first command must list `horizontalpodautoscalers`. Query only the metric
APIs used by the planned HPA; an API returning `NotFound` means its server or
adapter is unavailable.

## Choose the metric interface

Existing values remain canonical. The `metrics` value adds the native
`autoscaling/v2` MetricSpec interface without a second HPA namespace.

| `autoscaling.metrics` | Result |
| --- | --- |
| `null` or omitted | Build Resource metrics from `targetCPUUtilizationPercentage` and `targetMemoryUtilizationPercentage`. |
| Non-empty list | Use the supplied native Resource, ContainerResource, External, Object, or Pods metrics. |
| `[]` | Suppress percentage-derived Resource metrics. Use this for an HPA driven only by `hpaScalingRules`; rendering fails if no rules remain. |

Prometheus-backed `hpaScalingRules` always append generated External metrics to
the selected metric list.

## Configure CPU utilization

The released percentage interface continues to work:

```yaml
image:
  repository: ghcr.io/example/app
  tag: "1.2.3"

resources:
  requests:
    cpu: 100m
    memory: 128Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
```

For native `autoscaling/v2` metrics, set `metrics` directly:

```yaml
resources:
  requests:
    cpu: 100m

autoscaling:
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

The chart validates utilization requests for native metrics. Existing
percentage-based releases keep their historical rendering behavior, so audit
older workloads with `kubectl describe hpa` and add any missing requests.
Requests supplied through `extraContainerProps.resources` are also recognized
because the validator and Deployment use the same effective resource map.

Kubernetes calculates a desired replica count for every configured metric and
uses the highest result.

## Configure scaling behavior

Use the native v2 behavior shape:

```yaml
autoscaling:
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
the target cluster enables that feature.

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
  enabled: true
  minReplicas: 2
  maxReplicas: 20
  metrics: []
  hpaScalingRules:
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

The generated recording rule is labeled `hpa_metric: "true"`. The data path
is:

1. The application exposes the source metric.
2. Prometheus scrapes it and evaluates the recording rule.
3. Prometheus Adapter publishes the recorded series through
   `external.metrics.k8s.io`.
4. The HPA controller reads the External metric and changes Deployment
   replicas.

The `prometheusRule.additionalLabels` values must match the Prometheus
Operator's rule selector. The adapter must discover the `hpa_metric: "true"`
label; this chart does not configure either dependency.

Set these shell variables to the release namespace and metric name, then run
the read-only checks:

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
metric. If the final command returns `NotFound`, verify the recording series
and adapter configuration before changing the HPA target.

## Migrate draft nested values

The nested values proposed before this feature was released are intentionally
unsupported. If an experimental values file used them, migrate as follows:

| Draft value | Supported value |
| --- | --- |
| `autoscaling.horizontal.enabled` | `autoscaling.enabled` |
| `autoscaling.horizontal.minReplicas` | `autoscaling.minReplicas` |
| `autoscaling.horizontal.maxReplicas` | `autoscaling.maxReplicas` |
| `autoscaling.horizontal.annotations` | `autoscaling.annotations` |
| `autoscaling.horizontal.behavior` | `autoscaling.behavior` |
| `autoscaling.horizontal.metrics` | `autoscaling.metrics` |
| `autoscaling.horizontal.prometheusScalingRules` | `autoscaling.hpaScalingRules` |

The values schema rejects the draft paths so a stale experiment cannot be
silently ignored.

## Verify HPA operation

Set the namespace and rendered HPA name. With release name `example` and no
name overrides, the resource name is `example-universal-chart`.

```bash
NAMESPACE=example
HPA_NAME=example-universal-chart

kubectl get hpa -n "${NAMESPACE}" "${HPA_NAME}"
kubectl describe hpa -n "${NAMESPACE}" "${HPA_NAME}"
kubectl get events -n "${NAMESPACE}" \
  --field-selector involvedObject.name="${HPA_NAME}" \
  --sort-by=.lastTimestamp
```

A healthy HPA reports current metric values and the `AbleToScale`,
`ScalingActive`, and `ScalingLimited` conditions.

## Troubleshoot HPA

| Symptom | Check |
| --- | --- |
| CPU or memory shows `<unknown>` | Confirm Metrics Server health and matching requests on every relevant container. |
| A custom or external metric is missing | Query its metrics API directly and inspect adapter discovery rules. |
| A Prometheus-backed metric is absent | Confirm the PrometheusRule is selected, the recorded series exists, and the adapter exposes `hpa_metric: "true"` series. |
| Replica count never falls | Inspect stabilization windows, current metric values, and the HPA conditions. |
| Rendering reports no effective metric | Set a percentage target, a native metric, or at least one `hpaScalingRule`. |

## Roll back to fixed replicas

Set `autoscaling.enabled: false` and set `replicaCount` to the required fixed
capacity in the same values change. Render the chart before applying it and
confirm the Deployment contains `spec.replicas` and the HPA is absent.

After Argo CD or Helm applies the change, verify the Deployment replica count:

```bash
NAMESPACE=example
DEPLOYMENT_NAME=example-universal-chart

kubectl get deployment -n "${NAMESPACE}" "${DEPLOYMENT_NAME}"
kubectl get hpa -n "${NAMESPACE}" "${DEPLOYMENT_NAME}"
```
