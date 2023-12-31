{{/*
Expand the name of the chart.
*/}}
{{- define "nes-node-web.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "nes-node-web.fullname" -}}
  {{ default .Values.name .Release.Name }}
{{- end }}
{{/* 
{{- define "nes-node-web.fullname" -}}  
  {{- if .Values.name }}
  {{- .Values.name | trunc 63 | trimSuffix "-" }}
  {{- else }}
  {{- $name := default .Chart.Name .Values.nameOverride }}
  {{- if contains $name .Release.Name }}
  {{- .Release.Name | trunc 63 | trimSuffix "-" }}
  {{- else }}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
  {{- end }}
  {{- end }}
{{- end }}
*/}}


{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "nes-node-web.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "nes-node-web.labels" -}}
helm.sh/chart: {{ include "nes-node-web.chart" . }}
{{ include "nes-node-web.selectorLabels" . }}
{{- if .Values.version }}
app.kubernetes.io/version: {{ .Values.version | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}

{{- end }}


{{/*
Selector labels
*/}}
{{- define "nes-node-web.selectorLabels" -}}{{/*
app.kubernetes.io/name: {{ include "nes-node-web.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
*/}}{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "nes-node-web.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "nes-node-web.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
