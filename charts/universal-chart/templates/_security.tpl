{{/* Resolve the token default without treating an explicit false as unset. */}}
{{- define "universal-chart.automountServiceAccountToken" -}}
{{- if ne .Values.serviceAccount.automount nil -}}
{{- .Values.serviceAccount.automount -}}
{{- else -}}
{{- not (.Values.securityProfile | default dict).enabled -}}
{{- end -}}
{{- end -}}

{{/* Pod defaults also cover init containers; callers retain field overrides. */}}
{{- define "universal-chart.podSecurityContext" -}}
{{- $context := dict -}}
{{- if (.Values.securityProfile | default dict).enabled -}}
{{- $context = dict "runAsNonRoot" true "seccompProfile" (dict "type" "RuntimeDefault") -}}
{{- end -}}
{{- toYaml (mergeOverwrite $context (deepCopy (.Values.podSecurityContext | default dict))) -}}
{{- end -}}

{{/* With the profile enabled, legacy per-container fields override the baseline
and shared context here so the caller can omit the duplicate YAML property. */}}
{{- define "universal-chart.containerSecurityContext" -}}
{{- $context := deepCopy (.root.Values.securityContext | default dict) -}}
{{- if (.root.Values.securityProfile | default dict).enabled -}}
{{- $defaults := dict "allowPrivilegeEscalation" false "capabilities" (dict "drop" (list "ALL")) -}}
{{- $legacy := .extraProps.securityContext -}}
{{- if eq $legacy nil -}}
{{- $legacy = dict -}}
{{- end -}}
{{- if not (kindIs "map" $legacy) -}}
{{- fail "extraContainerProps.securityContext must be an object when securityProfile.enabled is true." -}}
{{- end -}}
{{- $context = mergeOverwrite $defaults $context (deepCopy $legacy) -}}
{{- end -}}
{{- toYaml $context -}}
{{- end -}}
