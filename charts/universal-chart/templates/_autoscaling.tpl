{{/*
Build the effective HorizontalPodAutoscaler configuration. A null native
metrics list preserves the released CPU and memory target behavior; any list,
including an empty list, replaces those generated Resource metrics.
*/}}
{{- define "universal-chart.autoscaling.effective" -}}
{{- $config := deepCopy (.Values.autoscaling | default dict) -}}
{{- $nativeMetrics := get $config "metrics" -}}
{{- $usesNativeMetrics := ne $nativeMetrics nil -}}
{{- $metrics := list -}}
{{- if $usesNativeMetrics -}}
  {{- $metrics = deepCopy ($nativeMetrics | default list) -}}
{{- else -}}
  {{- with get $config "targetCPUUtilizationPercentage" -}}
    {{- $metrics = append $metrics (dict
      "type" "Resource"
      "resource" (dict
        "name" "cpu"
        "target" (dict
          "type" "Utilization"
          "averageUtilization" .
        )
      )
    ) -}}
  {{- end -}}
  {{- with get $config "targetMemoryUtilizationPercentage" -}}
    {{- $metrics = append $metrics (dict
      "type" "Resource"
      "resource" (dict
        "name" "memory"
        "target" (dict
          "type" "Utilization"
          "averageUtilization" .
        )
      )
    ) -}}
  {{- end -}}
{{- end -}}
{{- $_ := set $config "metrics" $metrics -}}
{{- $_ := set $config "usesNativeMetrics" $usesNativeMetrics -}}
{{- toYaml $config -}}
{{- end }}

{{/*
Reject horizontal configurations that would render an inert or unsafe HPA.
Schema validation owns structural checks; this helper owns cross-field checks.
*/}}
{{- define "universal-chart.autoscaling.validate" -}}
{{- $root := .root -}}
{{- $config := .config -}}
{{- if $config.enabled -}}
  {{- $rules := $config.hpaScalingRules | default list -}}
  {{- if eq (add (len $config.metrics) (len $rules)) 0 -}}
    {{- fail "autoscaling: enabled requires at least one effective metric or hpaScalingRule" -}}
  {{- end -}}
  {{- if gt (int $config.minReplicas) (int $config.maxReplicas) -}}
    {{- fail (printf "autoscaling: minReplicas (%v) cannot exceed maxReplicas (%v)" $config.minReplicas $config.maxReplicas) -}}
  {{- end -}}
  {{/*
  Missing requests make a utilization metric inert rather than invalid, so
  this check only guards the new native metrics interface. Existing releases
  using the CPU and memory percentage fields retain their rendering behavior.
  */}}
  {{- if $config.usesNativeMetrics -}}
    {{- $resources := include "universal-chart.containerResources" $root | fromYaml -}}
    {{- $requests := get $resources "requests" | default dict -}}
    {{- range $index, $metric := $config.metrics -}}
      {{- if and (eq $metric.type "Resource") (eq $metric.resource.target.type "Utilization") -}}
        {{- $resourceName := $metric.resource.name -}}
        {{- if not (hasKey $requests $resourceName) -}}
          {{- fail (printf "autoscaling.metrics[%d]: Resource utilization for %s requires resources.requests.%s" $index $resourceName $resourceName) -}}
        {{- end -}}
      {{- else if and (eq $metric.type "ContainerResource") (eq $metric.containerResource.target.type "Utilization") (eq $metric.containerResource.container $root.Chart.Name) -}}
        {{- $resourceName := $metric.containerResource.name -}}
        {{- if not (hasKey $requests $resourceName) -}}
          {{- fail (printf "autoscaling.metrics[%d]: ContainerResource utilization for container %q and resource %s requires resources.requests.%s" $index $root.Chart.Name $resourceName $resourceName) -}}
        {{- end -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- end }}

{{/*
Render an External metric entry backed by a generated Prometheus recording
rule.
*/}}
{{- define "universal-chart.autoscaling.prometheusMetric" -}}
{{- $rule := .rule -}}
{{- $index := .index -}}
{{- $target := default dict $rule.target -}}
{{- $targetType := default "AverageValue" $target.type -}}
- type: External
  external:
    metric:
      name: {{ required (printf "autoscaling.hpaScalingRules[%d].name is required" $index) $rule.name | quote }}
      {{- with $rule.selector }}
      selector:
        matchLabels:
          {{- toYaml . | nindent 10 }}
      {{- end }}
    target:
      type: {{ $targetType }}
      {{- if eq $targetType "Value" }}
      value: {{ required (printf "autoscaling.hpaScalingRules[%d].target.value is required when target.type is Value" $index) $target.value | quote }}
      {{- else if eq $targetType "AverageValue" }}
      averageValue: {{ required (printf "autoscaling.hpaScalingRules[%d].target.averageValue is required when target.type is AverageValue" $index) $target.averageValue | quote }}
      {{- else }}
      {{- fail (printf "autoscaling.hpaScalingRules[%d].target.type must be Value or AverageValue" $index) }}
      {{- end }}
{{- end }}
