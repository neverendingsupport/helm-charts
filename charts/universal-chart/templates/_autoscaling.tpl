{{/*
Build the canonical HorizontalPodAutoscaler configuration. New horizontal
values override their legacy equivalents only when the new key is present.
*/}}
{{- define "universal-chart.autoscaling.horizontal" -}}
{{- $legacy := .Values.autoscaling | default dict -}}
{{- $horizontal := get $legacy "horizontal" | default dict -}}
{{- $effective := dict -}}
{{- range $key := list "enabled" "minReplicas" "maxReplicas" "annotations" "behavior" -}}
  {{- $value := get $legacy $key -}}
  {{- if hasKey $horizontal $key -}}
    {{- $value = get $horizontal $key -}}
  {{- end -}}
  {{- $_ := set $effective $key (deepCopy $value) -}}
{{- end -}}

{{- $metrics := list -}}
{{- if hasKey $horizontal "metrics" -}}
  {{- $metrics = deepCopy (get $horizontal "metrics") -}}
{{- else -}}
  {{- with get $legacy "targetCPUUtilizationPercentage" -}}
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
  {{- with get $legacy "targetMemoryUtilizationPercentage" -}}
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
{{- $_ := set $effective "metrics" $metrics -}}
{{- $_ := set $effective "metricsSource" (ternary "horizontal" "legacy" (hasKey $horizontal "metrics")) -}}

{{- $prometheusScalingRules := get $legacy "hpaScalingRules" | default list -}}
{{- if hasKey $horizontal "prometheusScalingRules" -}}
  {{- $prometheusScalingRules = get $horizontal "prometheusScalingRules" | default list -}}
{{- end -}}
{{- $_ := set $effective "prometheusScalingRules" (deepCopy $prometheusScalingRules) -}}
{{- toYaml $effective -}}
{{- end }}

{{/*
Reject horizontal configurations that would render an inert or unsafe HPA.
Schema validation owns structural checks; this helper owns cross-field checks.
*/}}
{{- define "universal-chart.autoscaling.validateHorizontal" -}}
{{- $root := .root -}}
{{- $config := .config -}}
{{- if $config.enabled -}}
  {{- $metricCount := add (len $config.metrics) (len $config.prometheusScalingRules) -}}
  {{- if eq $metricCount 0 -}}
    {{- fail "autoscaling.horizontal: enabled requires at least one metric or prometheusScalingRule" -}}
  {{- end -}}
  {{- if gt (int $config.minReplicas) (int $config.maxReplicas) -}}
    {{- fail (printf "autoscaling.horizontal: minReplicas (%v) cannot exceed maxReplicas (%v)" $config.minReplicas $config.maxReplicas) -}}
  {{- end -}}
  {{/*
  Missing requests make a utilization metric inert rather than invalid, so this
  check only guards the new interface. Legacy releases that inherit
  targetCPUUtilizationPercentage or targetMemoryUtilizationPercentage keep
  rendering as they did before autoscaling.horizontal existed.
  */}}
  {{- if eq $config.metricsSource "horizontal" -}}
    {{- $resources := include "universal-chart.containerResources" $root | fromYaml -}}
    {{- $requests := get $resources "requests" | default dict -}}
    {{- range $index, $metric := $config.metrics -}}
      {{- if and (eq $metric.type "Resource") (eq $metric.resource.target.type "Utilization") -}}
        {{- $resourceName := $metric.resource.name -}}
        {{- if not (hasKey $requests $resourceName) -}}
          {{- fail (printf "autoscaling.horizontal.metrics[%d]: Resource utilization for %s requires resources.requests.%s" $index $resourceName $resourceName) -}}
        {{- end -}}
      {{- else if and (eq $metric.type "ContainerResource") (eq $metric.containerResource.target.type "Utilization") (eq $metric.containerResource.container $root.Chart.Name) -}}
        {{- $resourceName := $metric.containerResource.name -}}
        {{- if not (hasKey $requests $resourceName) -}}
          {{- fail (printf "autoscaling.horizontal.metrics[%d]: ContainerResource utilization for container %q and resource %s requires resources.requests.%s" $index $root.Chart.Name $resourceName $resourceName) -}}
        {{- end -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- end }}

{{/*
Normalize a schema-validated Kubernetes quantity for VPA bound comparisons.
*/}}
{{- define "universal-chart.autoscaling.quantityFloat" -}}
{{- $quantity := toString . -}}
{{- $number := regexFind "^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)" $quantity -}}
{{- $suffix := trimPrefix $number $quantity -}}
{{- if regexMatch "^[eE][+-]?[0-9]+$" $suffix -}}
  {{- float64 $quantity -}}
{{- else -}}
  {{- $multipliers := dict
    "" "1"
    "n" "1e-9"
    "u" "1e-6"
    "m" "1e-3"
    "k" "1e3"
    "K" "1e3"
    "M" "1e6"
    "G" "1e9"
    "T" "1e12"
    "P" "1e15"
    "E" "1e18"
    "Ki" "1024"
    "Mi" "1048576"
    "Gi" "1073741824"
    "Ti" "1099511627776"
    "Pi" "1125899906842624"
    "Ei" "1152921504606846976"
  -}}
  {{- mulf (float64 $number) (float64 (get $multipliers $suffix)) -}}
{{- end -}}
{{- end }}

{{/*
Reject vertical configurations without explicit mutation bounds and prevent
request-based HPA/VPA feedback loops.
*/}}
{{- define "universal-chart.autoscaling.validateVertical" -}}
{{- $root := .root -}}
{{- $vertical := .vertical -}}
{{- $updatePolicy := $vertical.updatePolicy | default dict -}}
{{- $updateMode := $updatePolicy.updateMode | default "Off" -}}
{{- $isActive := ne $updateMode "Off" -}}
{{- $policies := $vertical.resourcePolicy.containerPolicies | default list -}}
{{- if and $isActive (eq (len $policies) 0) -}}
  {{- fail "autoscaling.vertical: active update modes require at least one containerPolicy with explicit resource ceilings" -}}
{{- end -}}
{{- $policyNames := dict -}}
{{- range $index, $policy := $policies -}}
  {{- if hasKey $policyNames $policy.containerName -}}
    {{- fail (printf "autoscaling.vertical.resourcePolicy.containerPolicies[%d]: duplicate containerName %q" $index $policy.containerName) -}}
  {{- end -}}
  {{- $_ := set $policyNames $policy.containerName true -}}
  {{- $policyMode := $policy.mode | default "Auto" -}}
  {{- $minAllowed := $policy.minAllowed | default dict -}}
  {{- $maxAllowed := $policy.maxAllowed | default dict -}}
  {{- range $resourceName := list "cpu" "memory" -}}
    {{- if and (hasKey $minAllowed $resourceName) (hasKey $maxAllowed $resourceName) -}}
      {{- $minimum := include "universal-chart.autoscaling.quantityFloat" (get $minAllowed $resourceName) | float64 -}}
      {{- $maximum := include "universal-chart.autoscaling.quantityFloat" (get $maxAllowed $resourceName) | float64 -}}
      {{- if gt $minimum $maximum -}}
        {{- fail (printf "autoscaling.vertical.resourcePolicy.containerPolicies[%d]: minAllowed.%s (%v) cannot exceed maxAllowed.%s (%v)" $index $resourceName (get $minAllowed $resourceName) $resourceName (get $maxAllowed $resourceName)) -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
  {{- if and $isActive (ne $policyMode "Off") -}}
    {{- $controlledResources := $policy.controlledResources | default list -}}
    {{- if eq (len $controlledResources) 0 -}}
      {{- fail (printf "autoscaling.vertical.resourcePolicy.containerPolicies[%d]: active VPA policies require controlledResources" $index) -}}
    {{- end -}}
    {{- range $resourceName := $controlledResources -}}
      {{- if not (hasKey $maxAllowed $resourceName) -}}
        {{- fail (printf "autoscaling.vertical.resourcePolicy.containerPolicies[%d]: active VPA policy for %s requires maxAllowed.%s" $index $resourceName $resourceName) -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}

{{- if $isActive -}}
  {{- $horizontal := include "universal-chart.autoscaling.horizontal" $root | fromYaml -}}
  {{- if $horizontal.enabled -}}
    {{- range $metricIndex, $metric := $horizontal.metrics -}}
      {{- if and (eq $metric.type "Resource") (eq $metric.resource.target.type "Utilization") -}}
        {{- range $policyIndex, $policy := $policies -}}
          {{- $policyMode := $policy.mode | default "Auto" -}}
          {{- if and (ne $policyMode "Off") (has $metric.resource.name ($policy.controlledResources | default list)) -}}
            {{- fail (printf "autoscaling.vertical: active VPA policy %d controls %s, which conflicts with autoscaling.horizontal.metrics[%d] Resource utilization" $policyIndex $metric.resource.name $metricIndex) -}}
          {{- end -}}
        {{- end -}}
      {{- else if and (eq $metric.type "ContainerResource") (eq $metric.containerResource.target.type "Utilization") -}}
        {{- range $policyIndex, $policy := $policies -}}
          {{- $policyMode := $policy.mode | default "Auto" -}}
          {{- $containerMatches := or (eq $policy.containerName "*") (eq $policy.containerName $metric.containerResource.container) -}}
          {{- if and (ne $policyMode "Off") $containerMatches (has $metric.containerResource.name ($policy.controlledResources | default list)) -}}
            {{- fail (printf "autoscaling.vertical: active VPA policy %d controls %s for container %q, which conflicts with autoscaling.horizontal.metrics[%d] ContainerResource utilization" $policyIndex $metric.containerResource.name $metric.containerResource.container $metricIndex) -}}
          {{- end -}}
        {{- end -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- end }}

{{/*
Render an External metric entry backed by a generated Prometheus recording rule.
*/}}
{{- define "universal-chart.autoscaling.prometheusMetric" -}}
{{- $rule := .rule -}}
{{- $index := .index -}}
{{- $target := default dict $rule.target -}}
{{- $targetType := default "AverageValue" $target.type -}}
- type: External
  external:
    metric:
      name: {{ required (printf "autoscaling prometheusScalingRules[%d].name is required" $index) $rule.name | quote }}
      {{- with $rule.selector }}
      selector:
        matchLabels:
          {{- toYaml . | nindent 10 }}
      {{- end }}
    target:
      type: {{ $targetType }}
      {{- if eq $targetType "Value" }}
      value: {{ required (printf "autoscaling prometheusScalingRules[%d].target.value is required when target.type is Value" $index) $target.value | quote }}
      {{- else if eq $targetType "AverageValue" }}
      averageValue: {{ required (printf "autoscaling prometheusScalingRules[%d].target.averageValue is required when target.type is AverageValue" $index) $target.averageValue | quote }}
      {{- else }}
      {{- fail (printf "autoscaling prometheusScalingRules[%d].target.type must be Value or AverageValue" $index) }}
      {{- end }}
{{- end }}
