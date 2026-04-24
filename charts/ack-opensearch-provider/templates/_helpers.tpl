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
{{- with .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ack-opensearch-provider.connectionSecretName" -}}
{{- default (printf "%s-connection" (include "ack-opensearch-provider.fullname" .)) .Values.connectionSecret.name -}}
{{- end -}}

{{- define "ack-opensearch-provider.connectionSecretAnnotationsJSON" -}}
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
{{- $annotations | toJson -}}
{{- end -}}

{{- define "ack-opensearch-provider.connectionSecretAnnotations" -}}
{{- $json := include "ack-opensearch-provider.connectionSecretAnnotationsJSON" . | trim -}}
{{- if and $json (ne $json "{}") -}}
{{- $annotations := fromJson $json -}}
{{- if gt (len $annotations) 0 -}}
{{- toYaml $annotations -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ack-opensearch-provider.connectionSecretMetadataMergePatchJSON" -}}
{{- $json := include "ack-opensearch-provider.connectionSecretAnnotationsJSON" . | trim -}}
{{- $annotations := dict -}}
{{- if and $json (ne $json "{}") -}}
{{- $annotations = fromJson $json -}}
{{- end -}}
{{- $reflectorAnnotationKeys := list
  "reflector.v1.k8s.emberstack.com/reflection-allowed"
  "reflector.v1.k8s.emberstack.com/reflection-auto-enabled"
  "reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces"
  "reflector.v1.k8s.emberstack.com/reflection-auto-namespaces"
-}}
{{- range $key := $reflectorAnnotationKeys -}}
{{- if not (hasKey $annotations $key) -}}
{{- $_ := set $annotations $key nil -}}
{{- end -}}
{{- end -}}
{{- if gt (len $annotations) 0 -}}
{{- dict "metadata" (dict "annotations" $annotations) | toJson -}}
{{- else -}}
{}
{{- end -}}
{{- end -}}

{{- define "ack-opensearch-provider.passwordGeneratorName" -}}
{{- printf "%s-password" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-opensearch-provider.externalSecretName" -}}
{{- printf "%s-auth" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-opensearch-provider.bootstrapServiceAccountName" -}}
{{- printf "%s-bootstrap" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-opensearch-provider.bootstrapRoleName" -}}
{{- printf "%s-bootstrap" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-opensearch-provider.bootstrapRoleBindingName" -}}
{{- printf "%s-bootstrap" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-opensearch-provider.secretBootstrapJobName" -}}
{{- printf "%s-bootstrap-secret" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}

{{- define "ack-opensearch-provider.endpointSyncJobName" -}}
{{- printf "%s-sync-connection" (include "ack-opensearch-provider.fullname" .) -}}
{{- end -}}
