{{- define "ack-opensearch-provider.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ack-opensearch-provider.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "ack-opensearch-provider.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ack-opensearch-provider.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "ack-opensearch-provider.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ack-opensearch-provider.connectionSecretName" -}}
{{- default (printf "%s-connection" (include "ack-opensearch-provider.fullname" .)) .Values.connectionSecret.name -}}
{{- end -}}

{{- define "ack-opensearch-provider.passwordGeneratorName" -}}
{{- printf "%s-password" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-opensearch-provider.externalSecretName" -}}
{{- printf "%s-auth" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-opensearch-provider.reflectorAnnotations" -}}
{{- if .Values.reflector.enabled }}
reflector.v1.k8s.emberstack.com/reflection-allowed: "true"
reflector.v1.k8s.emberstack.com/reflection-auto-enabled: "true"
{{- if .Values.reflector.allowedNamespaces }}
reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces: {{ join "," .Values.reflector.allowedNamespaces | quote }}
{{- end }}
{{- if .Values.reflector.pushNamespaces }}
reflector.v1.k8s.emberstack.com/reflection-auto-namespaces: {{ join "," .Values.reflector.pushNamespaces | quote }}
{{- end }}
{{- end }}
{{- end -}}
