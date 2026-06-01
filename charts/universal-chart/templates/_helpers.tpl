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
Render an External metric entry for a HorizontalPodAutoscaler.
*/}}
{{- define "universal-chart.hpa.externalMetric" -}}
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

{{/*
Render a HorizontalPodAutoscaler.
*/}}
{{- define "universal-chart.hpa" -}}
{{- $root := .root -}}
{{- $name := .name -}}
{{- $rules := default list .rules -}}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ $name | quote }}
  labels:
    {{- include "universal-chart.labels" $root | nindent 4 }}
  {{- with $root.Values.autoscaling.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "universal-chart.fullname" $root }}
  minReplicas: {{ $root.Values.autoscaling.minReplicas }}
  maxReplicas: {{ $root.Values.autoscaling.maxReplicas }}
  {{- with $root.Values.autoscaling.behavior }}
  behavior:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  metrics:
    {{- if $root.Values.autoscaling.targetCPUUtilizationPercentage }}
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ $root.Values.autoscaling.targetCPUUtilizationPercentage }}
    {{- end }}
    {{- if $root.Values.autoscaling.targetMemoryUtilizationPercentage }}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{ $root.Values.autoscaling.targetMemoryUtilizationPercentage }}
    {{- end }}
    {{- range $index, $rule := $rules }}
    {{- include "universal-chart.hpa.externalMetric" (dict "rule" $rule "index" $index) | nindent 4 }}
    {{- end }}
{{- end }}
