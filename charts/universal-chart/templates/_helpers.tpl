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
Render the application image reference from the tag or digest selected by the
values schema.
*/}}
{{- define "universal-chart.image" -}}
{{- $repository := .Values.image.repository -}}
{{- $tag := .Values.image.tag -}}
{{- $digest := .Values.image.digest -}}
{{- if $digest -}}
{{- printf "%s@%s" $repository $digest -}}
{{- else -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end }}

{{/*
Render the environment variable list shared by the main container, init
containers, and any extraContainers entries that inherit the environment.
Pass the root context.
*/}}
{{- define "universal-chart.containerEnv" -}}
# placeholder var so we can always make an env list
- name: REDIS_ENABLED
  value: {{ .Values.redis.enabled | quote }}
{{- if .Values.redis.enabled }}
- name: REDIS_USERNAME
  value: default # oddly hard-coded in chart
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ template "redis.secretName" .Subcharts.redis }}
      key: {{ template "redis.secretPasswordKey" .Subcharts.redis }}
- name: REDIS_PORT
  value: {{ .Values.redis.master.containerPorts.redis | quote }}
- name: REDIS_HOST
  value: {{ printf "%s-master" (include "common.names.fullname" .Subcharts.redis) }}
- name: REDIS_TLS
  value: {{ .Values.redis.tls.enabled | quote }}
{{- end }}
{{- range $k, $v := .Values.extraEnvVars }}
- name: {{ $k }}
  {{- if kindIs "map" $v }}
  {{- toYaml $v | nindent 2 }}
  {{- else }}
  value: {{ $v | quote }}
  {{- end }}
{{- end }}
{{- end }}

{{/*
Render the envFrom list shared by the main container, init containers, and any
extraContainers entries that inherit the environment. Empty output means the
envFrom key should be omitted. Pass the root context.
*/}}
{{- define "universal-chart.containerEnvFrom" -}}
{{- if .Values.awsEnvSecrets.externalSecret.secretPath }}
- secretRef:
    name: {{ .Values.awsEnvSecrets.env_secret_name }}
{{- end }}
{{- range .Values.extraEnvSecrets }}
- secretRef:
    name: {{ . }}
{{- end }}
{{- range .Values.extraEnvConfigmaps }}
- configMapRef:
    name: {{ . }}
{{- end }}
{{- end }}

{{/*
Render the image reference for one extraContainers entry from the tag or
digest selected by the values schema. Pass the entry's image map.
*/}}
{{- define "universal-chart.extraContainerImage" -}}
{{- if .digest -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end }}

{{/*
Render one extraContainers entry as a container spec list item.
Pass (dict "root" $ "container" <entry> "native" <bool>). Native entries are
rendered for the initContainers list and add restartPolicy: Always.
*/}}
{{- define "universal-chart.extraContainer" -}}
{{- $root := .root -}}
{{- $c := .container -}}
{{- $native := .native | default false -}}
{{- $inheritEnv := ternary $c.inheritEnv true (hasKey $c "inheritEnv") -}}
{{- $inheritVolumeMounts := ternary $c.inheritVolumeMounts true (hasKey $c "inheritVolumeMounts") -}}
- name: {{ $c.name }}
  image: {{ include "universal-chart.extraContainerImage" $c.image | quote }}
  imagePullPolicy: {{ $root.Values.image.pullPolicy }}
  {{- if $native }}
  restartPolicy: Always
  {{- end }}
  {{- with $c.command }}
  command:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $c.args }}
  args:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- $ownEnv := $c.env | default dict }}
  {{- $env := list }}
  {{- if $inheritEnv }}
  {{- range (include "universal-chart.containerEnv" $root | fromYamlArray) }}
  {{- if not (hasKey $ownEnv .name) }}
  {{- $env = append $env . }}
  {{- end }}
  {{- end }}
  {{- end }}
  {{- range $k, $v := $ownEnv }}
  {{- if kindIs "map" $v }}
  {{- $env = append $env (merge (dict "name" $k) $v) }}
  {{- else }}
  {{- $env = append $env (dict "name" $k "value" ($v | toString)) }}
  {{- end }}
  {{- end }}
  {{- with $env }}
  env:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- $envFrom := list }}
  {{- if $inheritEnv }}
  {{- with include "universal-chart.containerEnvFrom" $root | trim }}
  {{- $envFrom = fromYamlArray . }}
  {{- end }}
  {{- end }}
  {{- range ($c.envFromSecrets | default list) }}
  {{- $envFrom = append $envFrom (dict "secretRef" (dict "name" .)) }}
  {{- end }}
  {{- range ($c.envFromConfigmaps | default list) }}
  {{- $envFrom = append $envFrom (dict "configMapRef" (dict "name" .)) }}
  {{- end }}
  {{- with $envFrom }}
  envFrom:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- $securityContext := $c.securityContext | default dict }}
  {{- if not $securityContext }}
  {{- $securityContext = $root.Values.securityContext | default dict }}
  {{- end }}
  {{- with $securityContext }}
  securityContext:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $c.ports }}
  ports:
    {{- range . }}
    - name: {{ .name }}
      containerPort: {{ .containerPort }}
      protocol: {{ .protocol | default "TCP" }}
    {{- end }}
  {{- end }}
  {{- with $c.startupProbe }}
  startupProbe:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $c.livenessProbe }}
  livenessProbe:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $c.readinessProbe }}
  readinessProbe:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $c.resources }}
  resources:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- $ownMounts := $c.volumeMounts | default list }}
  {{- $ownMountPaths := list }}
  {{- range $ownMounts }}
  {{- $ownMountPaths = append $ownMountPaths .mountPath }}
  {{- end }}
  {{- $mounts := list }}
  {{- if $inheritVolumeMounts }}
  {{- range ($root.Values.volumeMounts | default list) }}
  {{- if not (has .mountPath $ownMountPaths) }}
  {{- $mounts = append $mounts . }}
  {{- end }}
  {{- end }}
  {{- end }}
  {{- $mounts = concat $mounts $ownMounts }}
  {{- with $mounts }}
  volumeMounts:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $c.extraContainerProps }}
  {{- toYaml . | nindent 2 }}
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
    {{- /* TODO: the Resource metrics below average utilization across every
    container in the pod, so extraContainers entries with resource requests
    dilute the signal from the main container. If someone actually needs
    sidecar-heavy pods to scale on the main container alone, add support for
    the ContainerResource metric type (targets one container by name). */}}
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
