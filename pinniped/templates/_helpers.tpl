{{- define "pinniped.namespace" -}}
{{- default .Release.Namespace .Values.namespace.name -}}
{{- end -}}

{{- define "pinniped.componentNamespace" -}}
{{- $root := .root -}}
{{- $component := .component -}}
{{- $baseNamespace := default "pinniped" $root.Values.namespace.name -}}
{{- printf "%s-%s" $baseNamespace $component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pinniped.componentName" -}}
{{- $root := .root -}}
{{- $component := .component -}}
{{- $values := index $root.Values $component -}}
{{- $defaultName := include "pinniped.componentNamespace" (dict "root" $root "component" $component) -}}
{{- default $defaultName $values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pinniped.standardLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name (.Chart.Version | replace "+" "_") }}
{{- end -}}

{{- define "pinniped.componentLabels" -}}
{{ include "pinniped.standardLabels" .root }}
app.kubernetes.io/component: {{ .component }}
app: {{ include "pinniped.componentName" . }}
{{- with .root.Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- with .componentValues.customLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "pinniped.runtimeLabels" -}}
app: {{ include "pinniped.componentName" . }}
{{- with .root.Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- with .componentValues.customLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "pinniped.componentSelectorLabels" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
app: {{ include "pinniped.componentName" . }}
{{- end -}}

{{- define "pinniped.image" -}}
{{- $image := .image -}}
{{- if $image.digest -}}
{{ printf "%s@%s" $image.repository $image.digest }}
{{- else -}}
{{ printf "%s:%s" $image.repository (default .root.Chart.AppVersion $image.tag) }}
{{- end -}}
{{- end -}}

{{- define "pinniped.concierge.serviceAccountName" -}}
{{- $base := include "pinniped.componentName" (dict "root" .root "component" "concierge") -}}
{{- if .suffix -}}
{{ printf "%s-%s" $base .suffix | trunc 63 | trimSuffix "-" }}
{{- else -}}
{{ $base }}
{{- end -}}
{{- end -}}

{{- define "pinniped.supervisor.serviceAccountName" -}}
{{ include "pinniped.componentName" (dict "root" .root "component" "supervisor") }}
{{- end -}}

{{- define "pinniped.concierge.proxyServiceName" -}}
{{ printf "%s-proxy" (include "pinniped.componentName" (dict "root" . "component" "concierge")) | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{- define "pinniped.concierge.apiTLSSecretName" -}}
{{- if .Values.concierge.tls.secretNames.api -}}
{{- .Values.concierge.tls.secretNames.api -}}
{{- else -}}
{{- printf "%s-api-tls-serving-certificate" (include "pinniped.componentName" (dict "root" . "component" "concierge")) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "pinniped.concierge.impersonationTLSSecretName" -}}
{{- if .Values.concierge.tls.secretNames.impersonationProxy -}}
{{- .Values.concierge.tls.secretNames.impersonationProxy -}}
{{- else -}}
{{- printf "%s-impersonation-proxy-tls-serving-certificate" (include "pinniped.componentName" (dict "root" . "component" "concierge")) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "pinniped.concierge.ingressServiceName" -}}
{{- if .Values.concierge.ingress.service.name -}}
{{- .Values.concierge.ingress.service.name -}}
{{- else -}}
{{ include "pinniped.concierge.proxyServiceName" . }}
{{- end -}}
{{- end -}}

{{- define "pinniped.concierge.gatewayServiceName" -}}
{{- if .Values.concierge.gatewayAPI.service.name -}}
{{- .Values.concierge.gatewayAPI.service.name -}}
{{- else -}}
{{ include "pinniped.concierge.ingressServiceName" . }}
{{- end -}}
{{- end -}}

{{- define "pinniped.supervisor.publicServiceName" -}}
{{- $base := include "pinniped.componentName" (dict "root" .root "component" "supervisor") -}}
{{- printf "%s-%s" $base .suffix | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pinniped.supervisor.autoClusterIPForExposure" -}}
{{- $ingress := include "pinniped.ingress" (dict "root" . "component" "supervisor") | fromYaml -}}
{{- $gateway := include "pinniped.gatewayAPI" (dict "root" . "component" "supervisor") | fromYaml -}}
{{- $needsBackend := or (and $ingress.enabled (not .Values.supervisor.ingress.service.name)) (and $gateway.enabled (not .Values.supervisor.gatewayAPI.service.name)) -}}
{{- if and .Values.supervisor.enabled $needsBackend (not .Values.supervisor.service.public.clusterIP.enabled) (not .Values.supervisor.service.public.loadBalancer.enabled) (not .Values.supervisor.service.public.nodePort.enabled) -}}
true
{{- else -}}
false
{{- end -}}
{{- end -}}

{{- define "pinniped.supervisor.exposureServiceName" -}}
{{- if .Values.supervisor.ingress.service.name -}}
{{- .Values.supervisor.ingress.service.name -}}
{{- else -}}
{{ include "pinniped.supervisor.defaultExposureServiceName" . }}
{{- end -}}
{{- end -}}

{{/* The Service an exposure uses when it names none: the first public Service that is on, else the API Service. */}}
{{- define "pinniped.supervisor.defaultExposureServiceName" -}}
{{- if .Values.supervisor.service.public.clusterIP.enabled -}}
{{ include "pinniped.supervisor.publicServiceName" (dict "root" . "suffix" "clusterip") }}
{{- else if eq (include "pinniped.supervisor.autoClusterIPForExposure" .) "true" -}}
{{ include "pinniped.supervisor.publicServiceName" (dict "root" . "suffix" "clusterip") }}
{{- else if .Values.supervisor.service.public.loadBalancer.enabled -}}
{{ include "pinniped.supervisor.publicServiceName" (dict "root" . "suffix" "loadbalancer") }}
{{- else if .Values.supervisor.service.public.nodePort.enabled -}}
{{ include "pinniped.supervisor.publicServiceName" (dict "root" . "suffix" "nodeport") }}
{{- else -}}
{{ printf "%s-api" (include "pinniped.componentName" (dict "root" . "component" "supervisor")) | trunc 63 | trimSuffix "-" }}
{{- end -}}
{{- end -}}

{{/*
The one TLS secret of the Supervisor, used by the cert-manager Certificate, the Supervisor config, the FederationDomain and
the ingress. cert-manager's certificate.secretName wins while cert-manager is on, then tls.secretName, then a generated name.
Resolving it in one place keeps the four in step without setting the same name in each.
*/}}
{{- define "pinniped.supervisor.defaultTLSSecretName" -}}
{{- $cm := include "pinniped.certManager" (dict "root" . "component" "supervisor") | fromYaml -}}
{{- $certificate := .Values.supervisor.tls.certManager.certificate -}}
{{- if and $cm.enabled $certificate.enabled $certificate.secretName -}}
{{- $certificate.secretName -}}
{{- else if .Values.supervisor.tls.secretName -}}
{{- .Values.supervisor.tls.secretName -}}
{{- else -}}
{{- printf "%s-default-tls-certificate" (include "pinniped.componentName" (dict "root" . "component" "supervisor")) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "pinniped.supervisor.ingressServiceName" -}}
{{ include "pinniped.supervisor.exposureServiceName" . }}
{{- end -}}

{{- define "pinniped.supervisor.gatewayServiceName" -}}
{{- if .Values.supervisor.gatewayAPI.service.name -}}
{{- .Values.supervisor.gatewayAPI.service.name -}}
{{- else -}}
{{ include "pinniped.supervisor.defaultExposureServiceName" . }}
{{- end -}}
{{- end -}}

{{/*
Settings both components share, resolved for one of them: the component's own value first, then `global`, then the
built-in default. A boolean left at null and a string left at "" in the component inherit, so an explicit
`false` or a value of its own always wins over `global`.
Call with (dict "root" $ "component" "concierge"|"supervisor"). Returns YAML, read it with `| fromYaml`.
*/}}
{{- define "pinniped.ingress" -}}
{{- $root := .root -}}
{{- $own := (index $root.Values .component).ingress -}}
{{- $global := $root.Values.global.ingress | default dict -}}
{{- $enabled := false -}}
{{- if not (kindIs "invalid" $own.enabled) -}}
{{- $enabled = $own.enabled -}}
{{- else if not (kindIs "invalid" $global.enabled) -}}
{{- $enabled = $global.enabled -}}
{{- end -}}
{{- $provider := $own.provider | default $global.provider | default "traefik" -}}
{{- if not (has $provider (list "traefik" "nginx")) -}}
{{- fail (printf "%s.ingress.provider (or global.ingress.provider) must be traefik or nginx, got %q. Gateway API is set under %s.gatewayAPI and global.gatewayAPI" .component $provider .component) -}}
{{- end -}}
{{- if hasKey $own "gatewayAPI" -}}
{{- fail (printf "%s.ingress.gatewayAPI moved to %s.gatewayAPI, and it no longer needs ingress.provider=gateway-api" .component .component) -}}
{{- end -}}
{{- $hostname := $own.hostname -}}
{{- if and (not $hostname) $root.Values.global.domain $own.hostPrefix -}}
{{- $hostname = printf "%s.%s" $own.hostPrefix $root.Values.global.domain -}}
{{- end -}}
enabled: {{ $enabled }}
provider: {{ $provider | quote }}
hostname: {{ $hostname | quote }}
{{- end -}}

{{/*
The Gateway API route of one component, resolved like `pinniped.ingress` but independent of it: `enabled` and `parentRefs`
come from the component, then `global.gatewayAPI`. The TLSRoute hostname is the component's `gatewayAPI.hostname`, then
the hostname the ingress would use. `hostnames` is the list the route renders, empty for a TCPRoute. `apiVersion` is the
component's own, else `v1` for a TLSRoute and `v1alpha2` for a TCPRoute.
Call with (dict "root" $ "component" "concierge"|"supervisor"). Returns YAML, read it with `| fromYaml`.
*/}}
{{- define "pinniped.gatewayAPI" -}}
{{- $root := .root -}}
{{- $own := (index $root.Values .component).gatewayAPI -}}
{{- $global := $root.Values.global.gatewayAPI | default dict -}}
{{- $enabled := false -}}
{{- if not (kindIs "invalid" $own.enabled) -}}
{{- $enabled = $own.enabled -}}
{{- else if not (kindIs "invalid" $global.enabled) -}}
{{- $enabled = $global.enabled -}}
{{- end -}}
{{- $ingress := include "pinniped.ingress" (dict "root" $root "component" .component) | fromYaml -}}
{{- $hostnames := list -}}
{{- if eq $own.routeKind "TLSRoute" -}}
{{- if $own.hostnames -}}
{{- $hostnames = $own.hostnames -}}
{{- else if or $own.hostname $ingress.hostname -}}
{{- $hostnames = list ($own.hostname | default $ingress.hostname) -}}
{{- end -}}
{{- end -}}
{{- $apiVersion := $own.apiVersion -}}
{{- if not $apiVersion -}}
{{- $apiVersion = ternary "gateway.networking.k8s.io/v1" "gateway.networking.k8s.io/v1alpha2" (eq $own.routeKind "TLSRoute") -}}
{{- end -}}
{{- dict "enabled" $enabled "apiVersion" $apiVersion "hostnames" $hostnames "parentRefs" ($own.parentRefs | default $global.parentRefs | default list) | toYaml -}}
{{- end -}}

{{- define "pinniped.certManager" -}}
{{- $root := .root -}}
{{- $own := (index $root.Values .component).tls.certManager -}}
{{- $global := $root.Values.global.certManager | default dict -}}
{{- $ownRef := $own.issuerRef | default dict -}}
{{- $globalRef := $global.issuerRef | default dict -}}
{{- $enabled := false -}}
{{- if not (kindIs "invalid" $own.enabled) -}}
{{- $enabled = $own.enabled -}}
{{- else if not (kindIs "invalid" $global.enabled) -}}
{{- $enabled = $global.enabled -}}
{{- end -}}
enabled: {{ $enabled }}
issuerName: {{ $ownRef.name | default $globalRef.name | quote }}
issuerKind: {{ $ownRef.kind | default $globalRef.kind | default "Issuer" | quote }}
issuerGroup: {{ $ownRef.group | default $globalRef.group | default "cert-manager.io" | quote }}
{{- end -}}

{{/*
Public issuer URL of the Supervisor: federationDomain.issuer, else https://<the Supervisor hostname>. Empty when neither
is known. The JWTAuthenticator uses it as its default issuer, because the two must match exactly.
*/}}
{{- define "pinniped.supervisor.issuer" -}}
{{- if .Values.supervisor.federationDomain.issuer -}}
{{- .Values.supervisor.federationDomain.issuer -}}
{{- else -}}
{{- $ingress := include "pinniped.ingress" (dict "root" . "component" "supervisor") | fromYaml -}}
{{- if $ingress.hostname -}}
{{- printf "https://%s" $ingress.hostname -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
certificate.dnsNames as a clean list, whichever way it was written. Helm's --set only builds a list from `[0]=name` or
`{name}`, and Argo CD hands over what you type as it is, so `name`, `[name]`, `["name"]` and `name,other` reach the
chart as strings. Brackets, quotes and spaces cannot be part of a host name, so they are dropped, and a comma
separates two names. Anything that is neither a string nor a list fails here, instead of rendering a Certificate that
cert-manager rejects.
Call with (dict "key" "<values path, for the error>" "names" <the value>). Returns YAML, read it with `| fromYamlArray`.
*/}}
{{- define "pinniped.dnsNames" -}}
{{- $names := .names -}}
{{- if kindIs "string" $names -}}
{{- $names = splitList "," $names -}}
{{- else if not (kindIs "slice" $names) -}}
{{- fail (printf "%s must be a list of host names, for example [app.example.com]" .key) -}}
{{- end -}}
{{- $clean := list -}}
{{- range $names -}}
{{- $name := toString . | trim | trimAll "[]\"' " -}}
{{- if $name -}}
{{- $clean = append $clean $name -}}
{{- end -}}
{{- end -}}
{{- toYaml $clean -}}
{{- end -}}
