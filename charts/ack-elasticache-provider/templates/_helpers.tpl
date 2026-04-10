{{- define "ack-elasticache-provider.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ack-elasticache-provider.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "ack-elasticache-provider.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ack-elasticache-provider.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "ack-elasticache-provider.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- with .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ack-elasticache-provider.connectionSecretName" -}}
{{- default (printf "%s-connection" (include "ack-elasticache-provider.fullname" .)) .Values.connectionSecret.name -}}
{{- end -}}

{{- define "ack-elasticache-provider.cacheParameterGroupName" -}}
{{- default (coalesce .Values.resourceName (include "ack-elasticache-provider.fullname" .)) .Values.cacheParameterGroup.name -}}
{{- end -}}

{{- define "ack-elasticache-provider.connectionSecretAnnotations" -}}
{{- $annotations := dict -}}
{{- if .Values.reflector.enabled -}}
{{- $_ := set $annotations "reflector.v1.k8s.emberstack.com/reflection-allowed" "true" -}}
{{- $_ := set $annotations "reflector.v1.k8s.emberstack.com/reflection-auto-enabled" "true" -}}
{{- if .Values.reflector.allowedNamespaces -}}
{{- $_ := set $annotations "reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces" (join "," .Values.reflector.allowedNamespaces) -}}
{{- end -}}
{{- if .Values.reflector.pushNamespaces -}}
{{- $_ := set $annotations "reflector.v1.k8s.emberstack.com/reflection-auto-namespaces" (join "," .Values.reflector.pushNamespaces) -}}
{{- end -}}
{{- end -}}
{{- range $key, $value := .Values.connectionSecret.annotations }}
{{- $_ := set $annotations $key $value -}}
{{- end -}}
{{- if gt (len $annotations) 0 -}}
{{- toYaml $annotations -}}
{{- end -}}
{{- end -}}

{{- define "ack-elasticache-provider.passwordGeneratorName" -}}
{{- printf "%s-password" (include "ack-elasticache-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-elasticache-provider.externalSecretName" -}}
{{- printf "%s-auth" (include "ack-elasticache-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-elasticache-provider.bootstrapServiceAccountName" -}}
{{- printf "%s-bootstrap" (include "ack-elasticache-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-elasticache-provider.bootstrapRoleName" -}}
{{- printf "%s-bootstrap" (include "ack-elasticache-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-elasticache-provider.bootstrapRoleBindingName" -}}
{{- printf "%s-bootstrap" (include "ack-elasticache-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-elasticache-provider.secretBootstrapJobName" -}}
{{- printf "%s-bootstrap-secret" (include "ack-elasticache-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-elasticache-provider.endpointSyncJobName" -}}
{{- printf "%s-sync-connection" (include "ack-elasticache-provider.fullname" .) -}}
{{- end -}}
