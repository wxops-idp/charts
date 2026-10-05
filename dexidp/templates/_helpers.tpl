{{/*
Full name of the wrapped Dex release. Mirrors the upstream `dex.fullname` logic (chart name `dex`),
so names rendered here line up with the Deployment/Service created by the Dex subchart.
*/}}
{{- define "dexidp.fullname" -}}
{{- if .Values.dex.fullnameOverride -}}
{{- .Values.dex.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default "dex" .Values.dex.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "dexidp.namespace" -}}
{{- .Values.dex.namespaceOverride | default (.Release.Namespace | trunc 63 | trimSuffix "-") -}}
{{- end -}}

{{- define "dexidp.labels" -}}
app.kubernetes.io/name: dex
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: wxops-idp
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{/*
Name of the Secret an ExternalSecret produces: `target.name` when set, otherwise `<dex fullname>-<key>`.
Call with (dict "root" $ "key" $key "es" $es).
*/}}
{{- define "dexidp.externalSecretName" -}}
{{- $name := dig "target" "name" "" .es -}}
{{- default (printf "%s-%s" (include "dexidp.fullname" .root) .key) $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
