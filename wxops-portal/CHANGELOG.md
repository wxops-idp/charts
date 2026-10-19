# wxops-portal changelog

## 0.1.1 - 2026-10-19

Same portal (0.5.2) and same image as 0.1.0, `ghcr.io/wxops-idp/wxops-portal:v0.5.2`. The image now follows `appVersion`.

### Changed
- `appVersion` is the exact image tag, `v0.5.2`, and the image is `<image.repository>:<appVersion>`. `image.tag` stays empty and only overrides it when set.
- The `app.kubernetes.io/version` label is `v0.5.2` instead of `0.5.2`, so pods roll once on upgrade. Everything else renders the same.

### Added
- A workflow opens a pull request when the portal publishes a release, setting `appVersion` to a tag it has confirmed in the registry.

## 0.1.0 - 2026-10-19

First release here, moved from the portal repository. Deploys W'xOps Portal 0.5.2. Install with `helm repo add wxops https://charts.wxops.cloud`.

### Added
- Standalone chart with no `common` dependency: Deployment, Service, ServiceAccount and optional RBAC.
- Secrets from External Secrets Operator: an `ExternalSecret` reads `OIDC_CLIENT_SECRET` and `SESSION_SECRET` from one store path, with configurable property names and room for extra secrets. `existingSecret` is the alternative.
- Traefik `IngressRoute` (plain HTTP by default) or a standard `Ingress` for ingress-nginx, Kong and others.
- A ConfigMap for the static cluster registry, mounted at `/etc/wxops/clusters.json`.
- Rendering fails and names the value when a required setting is missing: `env.FRONTEND_URL`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_REDIRECT_URI`, the secret store, or the ingress host.

### Changed
- The image is `ghcr.io/wxops-idp/wxops-portal` with the `v`-prefixed tag the portal publishes. The earlier chart used `ghcr.io/wxops/wxops-portal` and an unprefixed tag.
- Values moved out of the `portal:` prefix, see the migration table in the chart README.

### Fixed
- The portal starts on a default install. The earlier chart pointed `CLUSTERS_CONFIG_FILE` at a file it never created, and the backend exits without it.
