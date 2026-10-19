# wxops-portal

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.5.2](https://img.shields.io/badge/AppVersion-0.5.2-informational?style=flat-square)

A Helm chart for the W'xOps Portal, an Internal Developer Portal for Kubernetes-native platform teams, with secrets from External Secrets Operator and a Traefik IngressRoute.

See [CHANGELOG.md](./CHANGELOG.md) for release history.

>[!NOTE]
>This is a plain chart, not a wrapper. It deploys the [W'xOps Portal](https://github.com/wxops-idp/wxops-portal) container, pulls its secrets from a secret store through External Secrets Operator, and can be exposed through a Traefik `IngressRoute` or a standard `Ingress`. The chart version follows this repository, and `appVersion` is the portal release it deploys.

## What you need first

- **A Pinniped Supervisor** with an `OIDCClient` for the portal. The portal has no login of its own, see [Pinniped chart](../pinniped).
- **External Secrets Operator and a secret store** holding the portal's two secrets, or an existing Kubernetes Secret instead.
- **Traefik with its CRDs** if you use `ingressRoute`, or any ingress controller if you use `ingress`.

## Secrets from External Secrets Operator

The portal needs two secrets, `OIDC_CLIENT_SECRET` and `SESSION_SECRET`. The chart renders an `ExternalSecret` that reads them from one path in your store and creates the Secret the Deployment reads. Nothing secret lives in your values.

```text
OpenBao (KV v2)                  External Secrets Operator              Portal pod
wxops/portal                                                            envFrom
  oidc_client_secret  ──┐
  session_secret      ──┼──▶  ExternalSecret  ──▶  Secret  ──────────▶  OIDC_CLIENT_SECRET
                        │     (this chart)                              SESSION_SECRET
```

```bash
bao kv put -mount=wxops portal oidc_client_secret="<secret from the OIDCClient>" session_secret="$(openssl rand -hex 32)"
```

`SESSION_SECRET` must be exactly 64 hex characters. The path and property names are values: `externalSecret.path` is the secret in the store, and `externalSecret.properties` maps each environment variable to a property in it. Add any other secret the portal reads, for example `GITEA_TOKEN: gitea_token`. Set `externalSecret.properties: null` to extract the whole secret at the path instead, when its keys already are the environment variable names.

Without External Secrets Operator, set `externalSecret.enabled=false` and `existingSecret` to a Secret that has both keys.

## Exposing the portal

Both options are off by default. Set the public address in `env.FRONTEND_URL` and `env.OIDC_REDIRECT_URI` to match, because the portal uses them for CORS and for the login redirect.

**Traefik `IngressRoute`** (plain HTTP by default):

```yaml
ingressRoute:
  enabled: true
  host: portal.example.com
  # entryPoints: [websecure]
  # tls: {secretName: portal-tls}
```

**Standard `Ingress`**, for ingress-nginx, Kong, HAProxy or any other controller. The class and the controller-specific settings are yours:

```yaml
ingress:
  enabled: true
  className: nginx          # or kong, haproxy, ...
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: 10m
  hosts:
    - host: portal.example.com
  tls:
    - secretName: portal-tls
      hosts: [portal.example.com]
```

## Cluster registry

The backend refuses to start when `CLUSTERS_CONFIG_FILE` points to a missing file, so the chart creates a ConfigMap from `clusters.config` and sets that variable. An empty list is valid. Add your spoke clusters there, see `backend/clusters.example.json` in the portal repository. To discover clusters from Kubernetes Secrets instead, set `clusters.enabled=false` and `rbac.create=true`.

## Installing the Chart

```bash
helm repo add wxops https://charts.wxops.cloud
helm install wxops-portal wxops/wxops-portal -n wxops-system --create-namespace -f my-values.yaml
```

A minimal `my-values.yaml`:

```yaml
env:
  FRONTEND_URL: https://portal.example.com
  OIDC_ISSUER_URL: https://supervisor.example.com
  OIDC_CLIENT_ID: client.oauth.pinniped.dev-wxops-portal
  OIDC_REDIRECT_URI: https://portal.example.com/auth/callback

externalSecret:
  secretStoreRef:
    name: wxops-openbao

ingressRoute:
  enabled: true
  host: portal.example.com
```

The four `env` values and the secret store are required. A missing one fails the install with a message that names it.

For local rendering and testing:

```bash
helm template wxops-portal . -f values-test.yaml
helm lint . -f values-test.yaml
helm unittest .
```

## Upgrading to the latest portal

The chart's `appVersion` is the portal release it deploys, and the image tag is `v<appVersion>`. A scheduled workflow in this repository checks the portal's latest release every day and opens a pull request that bumps `appVersion`, the chart version and the changelog, so a new portal release reaches the chart repository after a person reviews and merges it. Install a newer chart version to get a newer portal, or set `image.tag` to pin another release. See the [CHANGELOG](./CHANGELOG.md) for which chart version carries which portal version.

## Migrating from the chart in the portal repository

The earlier chart was published to `oci://ghcr.io/wxops/wxops-portal/charts/wxops-portal` and was built on the `common` library chart. This one is standalone, so the values moved:

| Earlier chart (`portal.` prefix) | This chart |
| --- | --- |
| `portal.env.*` | `env.*` |
| `portal.image.*` | `image.*`, the default tag is now `v<appVersion>` |
| `portal.ingress.*` | `ingress.*`, or `ingressRoute.*` for Traefik |
| `portal.secretValues.*` with `extraManifests`, or `portal.envFrom` | `externalSecret.*`, or `existingSecret` |
| `portal.rbac.create` | `rbac.create` |
| `CLUSTERS_CONFIG_FILE` set, file not provided | `clusters.*`, the ConfigMap is created for you |

## Not yet verified on a cluster

The chart is linted, rendered and validated against the Kubernetes and CRD schemas, and its required parameters are covered by unit tests. These points still need a run on a real cluster:

- The portal starts with the generated `clusters.json` and the Secret from a real External Secrets Operator.
- The `IngressRoute` and the `Ingress` route login, the API and static assets correctly through your controller.
- The probes on `/healthz` and `/readyz` pass on the published image.

**Homepage:** <https://github.com/wxops-idp/wxops-portal>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| Xeus Nguyen | <xeusnguyen@gmail.com> | <https://wiki.xeusnguyen.xyz> |

## Source Code

* <https://github.com/wxops-idp/wxops-portal>

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` |  |
| clusters.config | object | `{"clusters":[]}` | Content of `clusters.json`. An empty list is valid. Each cluster needs at least `api_server`, see backend/clusters.example.json in the portal repository. |
| clusters.enabled | bool | `true` | Create a ConfigMap with the static cluster registry and point `CLUSTERS_CONFIG_FILE` at it. The backend fails to start when `CLUSTERS_CONFIG_FILE` points to a file that does not exist, so this stays on unless you use cluster discovery from Kubernetes Secrets (`rbac.create`) or set `CLUSTERS_CONFIG` yourself. |
| env | object | `{"FRONTEND_URL":"","OIDC_CLIENT_ID":"","OIDC_ISSUER_URL":"","OIDC_REDIRECT_URI":"","OIDC_SCOPES":"openid,groups,offline_access,username,pinniped:request-audience"}` | Non-secret configuration, passed to the container as environment variables with these exact names. The four values below are required and the chart fails to render without them. Every variable the backend reads is documented at https://github.com/wxops-idp/wxops-portal/blob/main/docs/getting-started/environment-variables.md |
| env.FRONTEND_URL | string | `""` | Public URL of the portal. Must equal what the browser sends as Origin, it is used for CORS. |
| env.OIDC_CLIENT_ID | string | `""` | Name of the Pinniped OIDCClient, `client.oauth.pinniped.dev-<suffix>`. |
| env.OIDC_ISSUER_URL | string | `""` | Issuer URL of the Pinniped Supervisor FederationDomain. The portal has no login of its own. |
| env.OIDC_REDIRECT_URI | string | `""` | OAuth2 redirect URI. Must match `redirectURIs` of the OIDCClient, normally `<FRONTEND_URL>/auth/callback`. |
| env.OIDC_SCOPES | string | `"openid,groups,offline_access,username,pinniped:request-audience"` | Scopes, must match the OIDCClient. `pinniped:request-audience` is needed for the hub and spoke token exchange. |
| existingSecret | string | `""` | Name of an existing Secret holding `OIDC_CLIENT_SECRET` and `SESSION_SECRET`, used when `externalSecret.enabled` is false. |
| externalSecret.annotations | object | `{}` | Annotations on the ExternalSecret. |
| externalSecret.apiVersion | string | `"external-secrets.io/v1"` | API version of the ExternalSecret. Use `external-secrets.io/v1beta1` if your operator does not serve `v1` yet. |
| externalSecret.enabled | bool | `true` | Create an ExternalSecret that builds the portal's Secret from a secret store such as OpenBao. When false, set `existingSecret`. |
| externalSecret.path | string | `"wxops/portal"` | Path of the secret in the store, relative to the store's mount. For OpenBao KV v2 this is the path below `data/`. |
| externalSecret.properties | object | `{"OIDC_CLIENT_SECRET":"oidc_client_secret","SESSION_SECRET":"session_secret"}` | Secret keys to read from that path, as `<environment variable>: <property in the stored secret>`. Add any other secret the portal needs, for example `GITEA_TOKEN: gitea_token`. Set `properties: null` to extract the whole secret at `path` instead, whose keys must then already be environment variable names. (An empty `{}` does not work, Helm merges maps with these defaults, only `null` removes them.) |
| externalSecret.refreshInterval | string | `"1h"` | How often External Secrets Operator re-reads the store. |
| externalSecret.secretName | string | `""` | Name of the Secret that External Secrets Operator creates. Defaults to `<fullname>-secrets`. |
| externalSecret.secretStoreRef.kind | string | `"ClusterSecretStore"` | Kind of the store: `SecretStore` or `ClusterSecretStore`. |
| externalSecret.secretStoreRef.name | string | `""` | Name of the SecretStore or ClusterSecretStore. Required when `externalSecret.enabled` is true. |
| extraEnv | list | `[]` | Extra environment variables as full `env` entries, for values that come from a field reference or another Secret. |
| extraEnvFrom | list | `[]` | Extra `envFrom` sources, for example another Secret or a ConfigMap. |
| fullnameOverride | string | `""` | Override the full resource name. |
| image.pullPolicy | string | `"IfNotPresent"` | Image pull policy. |
| image.repository | string | `"ghcr.io/wxops-idp/wxops-portal"` | Portal image. The portal repository publishes to GHCR under the wxops-idp organization. |
| image.tag | string | `""` | Image tag. Empty means `v<appVersion>`, which is how the portal tags its releases (`v0.5.2`, not `0.5.2`). |
| imagePullSecrets | list | `[]` | Image pull secrets, only needed for a private mirror. The published image is public. |
| ingress.annotations | object | `{}` | Annotations on the Ingress, where controller-specific settings go, for example `konghq.com/strip-path` or `nginx.ingress.kubernetes.io/proxy-body-size`. |
| ingress.className | string | `""` | IngressClass to use, for example `nginx` or `kong`. Empty uses the cluster default class. |
| ingress.enabled | bool | `false` | Create a standard Kubernetes Ingress, for any controller that implements it (ingress-nginx, Kong, HAProxy, a cloud load balancer, and so on). Use it instead of `ingressRoute`, or alongside it when two controllers serve different entry points. |
| ingress.hosts | list | `[]` | Hosts and paths to route, required when enabled. Each path defaults to `/` with `pathType: Prefix`. For example: `[{host: portal.example.com, paths: [{path: /, pathType: Prefix}]}]` |
| ingress.tls | list | `[]` | TLS settings, for example `[{secretName: portal-tls, hosts: [portal.example.com]}]`. Must match `env.FRONTEND_URL` when it is https. |
| ingressRoute.annotations | object | `{}` | Annotations on the IngressRoute. |
| ingressRoute.enabled | bool | `false` | Create a Traefik IngressRoute that sends HTTP requests to the portal. |
| ingressRoute.entryPoints | list | `["web"]` | Traefik entry points. `web` is plain HTTP, use `websecure` together with `tls` for HTTPS. |
| ingressRoute.host | string | `""` | Hostname to route, required when enabled. Ignored when `match` is set. |
| ingressRoute.match | string | `""` | Full Traefik rule. Defaults to Host(`<host>`). |
| ingressRoute.middlewares | list | `[]` | Traefik Middleware resources to apply, in order, each as `{name: ..., namespace: ...}` (`namespace` is optional). |
| ingressRoute.tls | object | `{}` | TLS settings of the route, rendered as is. Leave empty for plain HTTP, for example `{secretName: portal-tls}` or `{certResolver: letsencrypt}`. |
| nameOverride | string | `""` | Override the chart name used in resource names. |
| nodeSelector | object | `{}` | Node selector, tolerations and affinity for the portal pods. |
| podAnnotations | object | `{}` | Annotations on the portal pods. |
| podLabels | object | `{}` | Extra labels on the portal pods. |
| podSecurityContext | object | `{}` | Pod security context. The portal image runs nginx on port 80 as root, so none is set. Tighten it only after testing with your image. |
| probes | object | `{"liveness":{"failureThreshold":3,"httpGet":{"path":"/healthz","port":"http"},"periodSeconds":10},"readiness":{"failureThreshold":3,"httpGet":{"path":"/readyz","port":"http"},"periodSeconds":10}}` | Probes, using the portal's own health endpoints. The container exposes nginx on port 80, which proxies to the Go backend and Next.js. |
| rbac.create | bool | `false` | Create a Role and RoleBinding that let the portal read Secrets, for discovery of spoke clusters from Secrets in its own namespace. Turn `clusters.enabled` off when you use it. |
| replicaCount | int | `1` | Number of portal pods. The session cookie is encrypted with `SESSION_SECRET`, so every replica must get the same value, which a shared Secret already guarantees. |
| resources | object | `{"limits":{"memory":"512Mi"},"requests":{"cpu":"50m","memory":"256Mi"}}` | Resources for the portal container. |
| securityContext | object | `{}` | Container security context. See `podSecurityContext`. |
| service.annotations | object | `{}` | Annotations on the Service. |
| service.port | int | `80` | Service port. The container listens on port 80 (nginx). |
| service.type | string | `"ClusterIP"` | Service type. |
| serviceAccount.annotations | object | `{}` | Annotations on the ServiceAccount. |
| serviceAccount.create | bool | `true` | Create a ServiceAccount for the portal. |
| serviceAccount.name | string | `""` | Name of the ServiceAccount. Defaults to the full name when empty. |
| tolerations | list | `[]` |  |
