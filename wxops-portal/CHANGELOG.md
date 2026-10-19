# wxops-portal changelog

## 0.1.0 - 2026-10-19

First release in this repository. Moves the chart out of the `wxops-portal` repository so the latest portal is installable with `helm repo add wxops https://charts.wxops.cloud`. Deploys W'xOps Portal 0.5.2.

### Added
- A plain chart with no `common` dependency: Deployment, Service, ServiceAccount and optional RBAC.
- Secrets from External Secrets Operator: an `ExternalSecret` reads `OIDC_CLIENT_SECRET` and `SESSION_SECRET` from one path in the store, with the property names configurable and any extra secret addable. `existingSecret` is the alternative.
- Exposure through a Traefik `IngressRoute` (plain HTTP by default, with entry points, middlewares and TLS) or a standard `Ingress` for ingress-nginx, Kong and other controllers.
- A ConfigMap for the static cluster registry, mounted at `/etc/wxops/clusters.json`.
- The chart fails to render, naming the value, when `env.FRONTEND_URL`, `env.OIDC_ISSUER_URL`, `env.OIDC_CLIENT_ID`, `env.OIDC_REDIRECT_URI`, the secret store or the ingress host is missing.

### Changed
- The image is `ghcr.io/wxops-idp/wxops-portal` with the tag `v<appVersion>`, which is what the portal publishes. The earlier chart pointed to `ghcr.io/wxops/wxops-portal` with an unprefixed tag.
- Values moved out of the `portal:` prefix, see the migration table in the chart README.

### Fixed
- The portal no longer fails to start on a default install. The earlier chart set `CLUSTERS_CONFIG_FILE` to a file it never created, and the backend exits when that file is missing.
