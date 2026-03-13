{{/*
Expand the name of the chart.
*/}}
{{- define "universal-chart.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "universal-chart.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "universal-chart.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "universal-chart.labels" -}}
helm.sh/chart: {{ include "universal-chart.chart" . }}
{{ include "universal-chart.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "universal-chart.selectorLabels" -}}
app.kubernetes.io/name: {{ include "universal-chart.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "universal-chart.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "universal-chart.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Normalize awsEnvSecrets into a reusable list of generated ExternalSecrets.
*/}}
{{- define "universal-chart.awsEnvSecretEntries" -}}
{{- $items := list -}}
{{- $awsEnvSecrets := .Values.awsEnvSecrets | default dict -}}
{{- $legacyExternalSecret := $awsEnvSecrets.externalSecret | default dict -}}
{{- $legacySecretStoreRef := $legacyExternalSecret.secretStoreRef | default dict -}}
{{- if $legacyExternalSecret.secretPath }}
{{- $items = append $items (dict
  "env_secret_name" ($awsEnvSecrets.env_secret_name | default "aws-env")
  "externalSecret" (dict
    "secretPath" $legacyExternalSecret.secretPath
    "secretStoreRef" (dict
      "kind" ($legacySecretStoreRef.kind | default "SecretStore")
      "name" ($legacySecretStoreRef.name | default "aws-secrets-manager")
    )
  )
) -}}
{{- end }}
{{- range $secret := ($awsEnvSecrets.secrets | default list) }}
{{- $externalSecret := $secret.externalSecret | default dict -}}
{{- $secretStoreRef := $externalSecret.secretStoreRef | default dict -}}
{{- $items = append $items (dict
  "env_secret_name" $secret.env_secret_name
  "externalSecret" (dict
    "secretPath" $externalSecret.secretPath
    "secretStoreRef" (dict
      "kind" ($secretStoreRef.kind | default "SecretStore")
      "name" ($secretStoreRef.name | default "aws-secrets-manager")
    )
  )
) -}}
{{- end }}
{{- toYaml (dict "items" $items) -}}
{{- end }}
