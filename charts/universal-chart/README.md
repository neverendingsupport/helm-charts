# universal-chart

NES Universal Helm Chart

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square)

## Additional Information

This is supposedly a universal helm chart for "simple" apps.  It has a couple
of helpful extra features:
* built-in support for loading env vars from an AWS Secret Manager secret
* Bitnami redis chart

TODO: Explain how those work better

## Using The Chart

Normally, you're going to want to distribute this chart via ArgoCD as an
Application. Here's an example definition for "eol report card".

```yaml
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: &appname eol-report-card
  namespace: argocd
spec:
  project: eolds
  sources:
    - repoURL: https://github.com/neverendingsupport/eol-report-card.git
      path: infra/helm-chart/
      targetRevision: main
      helm:
        valueFiles:
          - $app_repo/infra/dev.values.yaml
        valuesObject:
          ingress:
            enabled: true
            className: nginx
            annotations:
              alb.ingress.kubernetes.io/ip-address-type: dualstack
              cert-manager.io/cluster-issuer: letsencrypt-prod
              nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
              forecastle.stakater.com/expose: "true"
              #forecastle.stakater.com/icon: "put a URL to an icon here someday"
            hosts:
              - host: eol-report-card.stage.apps.herodevs.io
                paths:
                  - path: /
                    pathType: Prefix
            tls:
              - secretName: erc-tls
                hosts:
                  - eol-report-card.stage.apps.herodevs.io
    - repoURL: https://github.com/neverendingsupport/eol-report-card.git
      targetRevision: main
      ref: app_repo

  destination:
    server: "https://kubernetes.default.svc"
    namespace: *appname
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - Validate=true
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - PruneLast=true
      - RespectIgnoreDifferences=true
    managedNamespaceMetadata:
      labels:
        use-ghcr-pull-secret: "true"

```

Of note: the ingress configuration always goes in the Argo Application, not in
your values YAML. An explanation of how Argo Applications work is documented
elsewhere (TODO: add link here)

## Requirements

| Repository | Name | Version |
|------------|------|---------|
| https://charts.bitnami.com/bitnami | redis | 21.0.2 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` | Select roughly specific nodes to run upon. This is similar to node selectors, but allows a bit more fuzziness and flexibility. More info at https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#affinity-and-anti-affinity |
| autoscaling | object | `{"enabled":false,"maxReplicas":10,"minReplicas":1,"targetCPUUtilizationPercentage":80,"targetMemoryUtilizationPercentage":null}` | section for configuring autoscaling. More information can be found here: https://kubernetes.io/docs/concepts/workloads/autoscaling/ |
| autoscaling.enabled | bool | `false` | enable autoscaling |
| autoscaling.maxReplicas | int | `10` | maximum number of replicas to run |
| autoscaling.minReplicas | int | `1` | miminum number of replicas to run |
| autoscaling.targetCPUUtilizationPercentage | int | `80` | If CPU utilization of replicas exceeds this percentage of requested CPU, start a new replica |
| autoscaling.targetMemoryUtilizationPercentage | string | `nil` | If Memory utilization of replicas exceeds this percentage of requested Memory, start a new replica |
| awsEnvSecrets.env_secret_name | string | `"aws-env"` | name of secret to store AWS secretmanager values within |
| awsEnvSecrets.externalSecret.secretPath | string | `""` | secret path |
| awsEnvSecrets.externalSecret.secretStoreRef.kind | string | `"SecretStore"` | This will either be SecretStore or ClusterSecretStore |
| awsEnvSecrets.externalSecret.secretStoreRef.name | string | `"aws-secrets-manager"` | name of the secret store; aws-secret-manager is usually right |
| fullnameOverride | string | `""` |  |
| image.pullPolicy | string | `"Always"` | k8s image pull policy - Always, Never, or IfNotPresent |
| image.repository | string | `nil` | repository path to image without tag name. Example: ghcr.io/neverendingsupport/universal-chart |
| image.tag | string | `nil` | tag / sha of image to pull |
| imagePullSecrets | list | `[]` |  |
| ingress | object | `{"annotations":{},"className":"","enabled":false,"hosts":[],"tls":[]}` | This block is for setting up the ingress. More information can be found here: https://kubernetes.io/docs/concepts/services-networking/ingress/ |
| ingress.annotations | object | `{}` | a map of annotations to define on the ingress resource |
| ingress.className | string | `""` | which ingress class to use (usually nginx, but could be alb) |
| ingress.enabled | bool | `false` | whether or not to use an ingress |
| ingress.hosts | list | `[]` | list of host blocks to listen on; host blocks define more than just a hostname hosts.host -- a hostname to listen upon. If TLS is enabled, the host will be selected via SNI. hosts.paths -- List of path rules.  Normally you want the root for a hostname to go to the root of your app, and the example commented above works well for that. |
| ingress.tls | list | `[]` | list of TLS certs to use.  The objects in the list have a secret name where the cert will be stored and a list of hosts to include in that cert. Normally this will only be a one item list, but it's technically acceptable to create multiple certs. If ingress.tls.secretName isn't specified, the secret will just be named "tls". |
| livenessProbe.httpGet.path | string | `"/"` |  |
| livenessProbe.httpGet.port | string | `"http"` |  |
| nameOverride | string | `""` |  |
| nodeSelector | object | `{}` | Select specific nodes to run upon Normally this should be an empty map |
| podAnnotations | object | `{}` | Add additional annotations to the pod. Annotations are generally for "people" uses and interoperability. For more information check out: https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/ |
| podLabels | object | `{}` | Add additional labels to the pods. Labels are generally for k8s internal use (pod selectors, etc) For more information check out: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/ |
| podSecurityContext | object | `{}` |  |
| readinessProbe.httpGet.path | string | `"/"` |  |
| readinessProbe.httpGet.port | string | `"http"` |  |
| redis | object | `{"auth":{"enabled":true,"usePasswordFiles":false},"enabled":false,"metrics":{"enabled":true,"prometheusRule":{"enabled":true,"rules":[{"alert":"RedisDown","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is down","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} down"},"expr":"redis_up{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} == 0","for":"2m","labels":{"severity":"error"}},{"alert":"RedisMemoryHigh","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is using {{ \"{{ $value }}\" }}% of its available memory.\n","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is using too much memory"},"expr":"redis_memory_used_bytes{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} * 100 / redis_memory_max_bytes{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} > 90\n","for":"2m","labels":{"severity":"error"}},{"alert":"RedisKeyEviction","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} has evicted {{ \"{{ $value }}\" }} keys in the last 5 minutes.\n","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} has evicted keys"},"expr":"increase(redis_evicted_keys_total{service=\"{{ template \"common.names.fullname\" . }}-metrics\"}[5m]) > 0\n","for":"1s","labels":{"severity":"error"}}]},"serviceMonitor":{"enabled":true}},"replica":{"replicaCount":3},"sentinel":{"enabled":false,"quorum":2}}` | Redis subchart configuration values. Default values are at https://artifacthub.io/packages/helm/bitnami/redis |
| redis.auth | object | `{"enabled":true,"usePasswordFiles":false}` | beware: overriding auth in your values file might be a mistake |
| redis.enabled | bool | `false` | whether or not to enable the Bitnami Redis helm chart |
| redis.metrics | object | `{"enabled":true,"prometheusRule":{"enabled":true,"rules":[{"alert":"RedisDown","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is down","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} down"},"expr":"redis_up{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} == 0","for":"2m","labels":{"severity":"error"}},{"alert":"RedisMemoryHigh","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is using {{ \"{{ $value }}\" }}% of its available memory.\n","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is using too much memory"},"expr":"redis_memory_used_bytes{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} * 100 / redis_memory_max_bytes{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} > 90\n","for":"2m","labels":{"severity":"error"}},{"alert":"RedisKeyEviction","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} has evicted {{ \"{{ $value }}\" }} keys in the last 5 minutes.\n","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} has evicted keys"},"expr":"increase(redis_evicted_keys_total{service=\"{{ template \"common.names.fullname\" . }}-metrics\"}[5m]) > 0\n","for":"1s","labels":{"severity":"error"}}]},"serviceMonitor":{"enabled":true}}` | Prometheus Metrics enabled for redis by default |
| redis.metrics.prometheusRule.rules | list | `[{"alert":"RedisDown","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is down","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} down"},"expr":"redis_up{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} == 0","for":"2m","labels":{"severity":"error"}},{"alert":"RedisMemoryHigh","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is using {{ \"{{ $value }}\" }}% of its available memory.\n","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} is using too much memory"},"expr":"redis_memory_used_bytes{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} * 100 / redis_memory_max_bytes{service=\"{{ template \"common.names.fullname\" . }}-metrics\"} > 90\n","for":"2m","labels":{"severity":"error"}},{"alert":"RedisKeyEviction","annotations":{"description":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} has evicted {{ \"{{ $value }}\" }} keys in the last 5 minutes.\n","summary":"Redis(R) instance {{ \"{{ $labels.instance }}\" }} has evicted keys"},"expr":"increase(redis_evicted_keys_total{service=\"{{ template \"common.names.fullname\" . }}-metrics\"}[5m]) > 0\n","for":"1s","labels":{"severity":"error"}}]` | default rules from the Bitnami chart :shrug: |
| redis.replica | object | `{"replicaCount":3}` | HA needs multiple replicas |
| redis.replica.replicaCount | int | `3` | number of replicas. This should be an odd number. |
| redis.sentinel.enabled | bool | `false` | sentinel mode requires client connection changes |
| redis.sentinel.quorum | int | `2` | number of sentinel nodes which need to agree This should be replicas/2+1 (3 replicas = 2, 5 replicas = 3, etc) |
| replicaCount | int | `1` | set a fixed number of replicas in the deployment This value is ignored if autoscaling is enabled |
| resources | object | `{}` | resource requests and limits. typically you can accept the values commented below, but ideally you'd run this in dev with some synthetic load and then either check on the monitoring values from Grafana or look at the Vertical Pod Autoscaler's recomendations via Goldilocks. |
| securityContext | object | `{}` |  |
| service | object | `{"port":3000,"type":"ClusterIP"}` | A "service" is basically a named port which follows a pod or pods; you should always use a service when networking in k8s. More information can be found here: https://kubernetes.io/docs/concepts/services-networking/service/ |
| service.port | int | `3000` | Defines the port the service listens upon. This is the *external* port exposed by the container, not necessarily the internal port inside the container.  It also doesn't have to be 80 or 443; an ingress (if used) will listen on a differnet port and communicate with the container on this service/port combination. more information can be found here: https://kubernetes.io/docs/concepts/services-networking/service/#field-spec-ports |
| service.type | string | `"ClusterIP"` | Define the service type more information can be found here: https://kubernetes.io/docs/concepts/services-networking/service/#publishing-services-service-types |
| serviceAccount.annotations | object | `{}` |  |
| serviceAccount.automount | bool | `true` |  |
| serviceAccount.create | bool | `true` |  |
| serviceAccount.name | string | `""` |  |
| tolerations | list | `[]` | List of taints these pods should tolerate. Normally this should be an empty list |
| volumeMounts | list | `[]` | Additional volumes to mount |
| volumes | list | `[]` | Additional volumes to create |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
