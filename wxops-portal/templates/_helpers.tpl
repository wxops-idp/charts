{{/*
Chart name, truncated to the 63 characters Kubernetes allows in a name label.
*/}}
{{- define "wxops-portal.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Full resource name: the release name, plus the chart name unless the release name already contains it.
*/}}
{{- define "wxops-portal.fullname" -}}
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

{{- define "wxops-portal.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "wxops-portal.selectorLabels" -}}
app.kubernetes.io/name: {{ include "wxops-portal.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "wxops-portal.labels" -}}
helm.sh/chart: {{ include "wxops-portal.chart" . }}
{{ include "wxops-portal.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: wxops-portal
{{- end }}

{{- define "wxops-portal.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "wxops-portal.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference. The portal tags its images with a leading v (v0.5.2), so the default tag is v<appVersion>.
*/}}
{{- define "wxops-portal.image" -}}
{{- printf "%s:%s" .Values.image.repository (default (printf "v%s" .Chart.AppVersion) .Values.image.tag) }}
{{- end }}

{{/*
Name of the Secret that holds OIDC_CLIENT_SECRET and SESSION_SECRET: the one External Secrets Operator creates, or an existing one.
*/}}
{{- define "wxops-portal.secretName" -}}
{{- if .Values.externalSecret.enabled }}
{{- default (printf "%s-secrets" (include "wxops-portal.fullname" .)) .Values.externalSecret.secretName }}
{{- else }}
{{- .Values.existingSecret }}
{{- end }}
{{- end }}

{{/*
Fail early, with the name of the value to set, instead of rendering a portal that cannot start.
*/}}
{{- define "wxops-portal.validate" -}}
{{- range $key := list "FRONTEND_URL" "OIDC_ISSUER_URL" "OIDC_CLIENT_ID" "OIDC_REDIRECT_URI" }}
{{- if not (get $.Values.env $key) }}
{{- fail (printf "env.%s is required: set it under `env` in your values" $key) }}
{{- end }}
{{- end }}
{{- if .Values.externalSecret.enabled }}
{{- if not .Values.externalSecret.secretStoreRef.name }}
{{- fail "externalSecret.secretStoreRef.name is required when externalSecret.enabled is true" }}
{{- end }}
{{- if not .Values.externalSecret.path }}
{{- fail "externalSecret.path is required when externalSecret.enabled is true" }}
{{- end }}
{{- else if not .Values.existingSecret }}
{{- fail "set externalSecret.enabled=true, or existingSecret to a Secret holding OIDC_CLIENT_SECRET and SESSION_SECRET" }}
{{- end }}
{{- if .Values.ingress.enabled }}
{{- if not .Values.ingress.hosts }}
{{- fail "ingress.hosts is required when ingress.enabled is true, for example [{host: portal.example.com}]" }}
{{- end }}
{{- range $index, $entry := .Values.ingress.hosts }}
{{- if not $entry.host }}
{{- fail (printf "ingress.hosts[%d].host is required" $index) }}
{{- end }}
{{- end }}
{{- end }}
{{- if and .Values.ingressRoute.enabled (not .Values.ingressRoute.host) (not .Values.ingressRoute.match) }}
{{- fail "ingressRoute.host (or ingressRoute.match) is required when ingressRoute.enabled is true" }}
{{- end }}
{{- end }}
