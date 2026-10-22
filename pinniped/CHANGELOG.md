# pinniped changelog

## 0.2.0 - 2026-10-22

Shared settings move under `global`, and the Pinniped CRDs come from `crds/` only, once.

### Added
- A `global` block for what both components share: `domain`, `certManager` (enabled and issuer) and `ingress` (enabled and provider). A component's own value wins, then `global`, then the default. A component boolean at `null` and a string at `""` inherit. See "Global values" in the README.
- Gateway API has its own values and templates, `<component>.gatewayAPI` and `global.gatewayAPI`, apart from `ingress`. It adds its own `annotations`, `hostname` and `service.{name,port}`, an `enabled` that inherits `global.gatewayAPI.enabled` at `null`, and `parentRefs` that can be set once under `global`. Enabling it without a `parentRefs` entry now fails and names the key.
- `ingress.hostPrefix` on both components. An empty `ingress.hostname` becomes `<hostPrefix>.<global.domain>`.
- The `FederationDomain` issuer defaults to `https://<supervisor hostname>`, and the `JWTAuthenticator` issuer defaults to the Supervisor's, so neither has to be set when a hostname or domain is.

### Changed
- `*.gatewayAPI.apiVersion` is empty by default and follows the route kind, `gateway.networking.k8s.io/v1` for a `TLSRoute` and `v1alpha2` for a `TCPRoute`. The old default, `v1beta1`, is not served for either kind, so the route was rejected unless `apiVersion` was set. Set it if your Gateway API CRDs serve another version.
- `tls.certManager.enabled` and `ingress.enabled` default to `null`, and `tls.certManager.issuerRef.kind`, `.group` and `ingress.provider` to `""`, to inherit from `global`. With `global` unset the rendered manifests are the same as in 0.1.1, except for the fix below.
- The impersonation proxy defaults to `ClusterIP`, and the AWS idle timeout annotation is no longer set. `concierge.credentialIssuer.impersonationProxy.service.type` was `LoadBalancer`, so Pinniped created a cloud load balancer; it now creates a cluster-internal Service. The README explains how `externalEndpoint` and an ingress expose it.
- To leave the CRDs out, use `helm install --skip-crds` or Argo CD `helm.skipCrds: true`. The README has a new "Installing the CRDs" section for the first install, a second install, upgrading the CRDs, Argo CD and uninstalling.

### Fixed
- The Supervisor's TLS secret is resolved once. Before, `supervisor.tls.certManager.certificate.secretName` changed only the Certificate and the ingress, while the `FederationDomain` and the Supervisor's `defaultTLSCertificateSecret` kept pointing at the generated name, so the secret had to be repeated in three places.
- `certificate.dnsNames` is turned into a list whichever way it is written: a single name, `[name]`, `["name"]` or `a,b`. Before, a string rendered as a bare scalar without the `-`, which cert-manager rejects, and `--set` never builds a list from `[...]`. A value that is neither a name nor a list now fails and names the key.

### Removed
- `concierge.ingress.hosts` and `concierge.ingress.tls`. No template read them. A leftover value is ignored.
- `*.ingress.gatewayAPI`, and `gateway-api` as an `ingress.provider`. Both fail the render and name `*.gatewayAPI`. The unused `sectionName` is gone: put it in a `parentRefs` entry.
- The `installCRDs` value and `templates/crds.yaml`. They rendered the same CRDs a second time next to `crds/`, which failed with `exists and cannot be imported into the current release` on Helm and listed every CRD twice in Argo CD. A leftover `installCRDs` in your values is ignored.

### Upgrade notes
- If you rely on the Concierge impersonation proxy load balancer, set `concierge.credentialIssuer.impersonationProxy.service.type: LoadBalancer` (and the annotations you need) before upgrading. Otherwise Pinniped replaces the load balancer with a `ClusterIP` Service and the external address stops working.
- Only if you use Gateway API: move `*.ingress.gatewayAPI.*` to `*.gatewayAPI.*`, drop `*.ingress.provider: gateway-api`, and set `*.gatewayAPI.enabled: true`. `*.ingress.annotations` no longer reach the route, use `*.gatewayAPI.annotations`. The README has an example.
- Only if you ran Helm with `installCRDs=true` and `--skip-crds`, the release owns the CRDs and the upgrade would delete them. Annotate them with `helm.sh/resource-policy=keep` first, the README has the commands. Argo CD users are not affected.

## 0.1.1 - 2026-10-16

### Added

- Refine readme with couple new values and name of chart for easier pull and apply

## 0.1.0 - 2026-10-05

First release. Pinniped Supervisor and Concierge (v0.46.0) for Kubernetes authentication, with Traefik, NGINX,
Gateway API and LoadBalancer exposure, optional cert-manager TLS, and Dex, GitHub and LDAP identity providers.
