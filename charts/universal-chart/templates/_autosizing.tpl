{{/*
Reject autosizing configurations that would create competing controllers or
activate VPA without explicit mutation bounds.
*/}}
{{- define "universal-chart.autosizing.validate" -}}
{{- $root := .root -}}
{{- $config := .config -}}
{{- if and $config.enabled $root.Values.autoscaling.enabled -}}
  {{- fail "autoscaling.enabled and autosizing.enabled are mutually exclusive; choose either HPA autoscaling or VPA autosizing" -}}
{{- end -}}
{{- if $config.enabled -}}
  {{- $updatePolicy := $config.updatePolicy | default dict -}}
  {{- $updateMode := $updatePolicy.updateMode | default "Off" -}}
  {{- $isActive := ne $updateMode "Off" -}}
  {{- $policies := $config.resourcePolicy.containerPolicies | default list -}}
  {{- if and $isActive (eq (len $policies) 0) -}}
    {{- fail "autosizing: active update modes require at least one containerPolicy with explicit resource ceilings" -}}
  {{- end -}}
  {{- $policyNames := dict -}}
  {{- range $index, $policy := $policies -}}
    {{- if hasKey $policyNames $policy.containerName -}}
      {{- fail (printf "autosizing.resourcePolicy.containerPolicies[%d]: duplicate containerName %q" $index $policy.containerName) -}}
    {{- end -}}
    {{- $_ := set $policyNames $policy.containerName true -}}
    {{- $policyMode := $policy.mode | default "Auto" -}}
    {{- if and $isActive (ne $policyMode "Off") -}}
      {{- $controlledResources := $policy.controlledResources | default list -}}
      {{- $maxAllowed := $policy.maxAllowed | default dict -}}
      {{- if eq (len $controlledResources) 0 -}}
        {{- fail (printf "autosizing.resourcePolicy.containerPolicies[%d]: active VPA policies require controlledResources" $index) -}}
      {{- end -}}
      {{- range $resourceName := $controlledResources -}}
        {{- if not (hasKey $maxAllowed $resourceName) -}}
          {{- fail (printf "autosizing.resourcePolicy.containerPolicies[%d]: active VPA policy for %s requires maxAllowed.%s" $index $resourceName $resourceName) -}}
        {{- end -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- end }}
