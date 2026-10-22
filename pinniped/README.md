# pinniped

![Version: 0.2.0](https://img.shields.io/badge/Version-0.2.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: v0.46.0](https://img.shields.io/badge/AppVersion-v0.46.0-informational?style=flat-square)

A Helm chart for Pinniped, a Kubernetes authentication via ImpersonationProxy with Supervisor and Concierge components.

>[!NOTE]
>This chart bootstraps the Pinniped Concierge and Supervisor server-side resources on Kubernetes. It ships the Pinniped CRDs in its `crds/` folder, and Helm installs them before everything else. They are not a value: to leave them out, use `helm install --skip-crds` or the Argo CD option `skipCrds`, see [Installing the CRDs](#installing-the-crds).
>The main customization surface lives in `values.yaml` under the `concierge` and `supervisor` sections.

## Global values

Both components need many of the same settings: the hostname, the cert-manager issuer, ingress on or off, the TLS secret, the issuer URL. Set them once under `global` instead of once per component. The order is: the component's own value, then `global`, then the built-in default. A boolean left at `null` and a string left at `""` in a component inherit, so an explicit `false` or a value of its own always wins.

| `global` key | Used for | Component keys that override it |
| --- | --- | --- |
| `domain` | Hostnames `<hostPrefix>.<domain>`: `supervisor.<domain>`, and `concierge.<domain>` unless you change `concierge.ingress.hostPrefix`. | `<component>.ingress.hostname` |
| `certManager.enabled` | Create the cert-manager `Certificate` of both components. | `<component>.tls.certManager.enabled` |
| `certManager.issuerRef.name`, `.kind`, `.group` | The issuer of both Certificates. | `<component>.tls.certManager.issuerRef.*` |
| `ingress.enabled` | Expose both components. | `<component>.ingress.enabled` |
| `ingress.provider` | `traefik` or `nginx`. | `<component>.ingress.provider` |
| `gatewayAPI.enabled` | Render a Gateway API route for both components. Independent of `ingress`. | `<component>.gatewayAPI.enabled` |
| `gatewayAPI.parentRefs` | The Gateways both routes attach to. | `<component>.gatewayAPI.parentRefs` |

Values that must be identical by nature are derived, so you do not repeat them:

- The Certificate `dnsNames` are the component hostname.
- The `FederationDomain` issuer is `https://<supervisor hostname>`, unless `supervisor.federationDomain.issuer` is set.
- The `JWTAuthenticator` issuer is the Supervisor's issuer, because the two must match exactly, unless `concierge.jwtAuthenticator.issuer` is set. Set it when the Supervisor runs on another cluster.
- The Supervisor's TLS secret is one name for the Certificate, the Supervisor config, the `FederationDomain` and the ingress: `supervisor.tls.certManager.certificate.secretName` while cert-manager is on, otherwise `supervisor.tls.secretName`, otherwise a generated name.

```yaml
global:
  domain: wxops.10-0-0-5.nip.io
  certManager:
    enabled: true
    issuerRef:
      name: wxops-idp-ca-issuer
      kind: ClusterIssuer
  ingress:
    enabled: true

concierge:
  ingress:
    hostPrefix: cp            # cp.wxops.10-0-0-5.nip.io
  jwtAuthenticator:
    create: true
    audience: hub-cluster

supervisor:
  federationDomain:
    create: true              # issuer https://supervisor.wxops.10-0-0-5.nip.io
```

That renders both Certificates, both Traefik routes, the `FederationDomain` and a `JWTAuthenticator` with the same issuer, with no hostname repeated.

## Networking requirements

Pinniped expects end-to-end TLS. When exposing the Supervisor or Concierge through an ingress controller, use TCP/TLS passthrough instead of regular Layer 7 HTTP termination.

This chart supports four exposure patterns per component:

- `traefik`: renders an `IngressRouteTCP` with `tls.passthrough=true`. This is the recommended option because it is a native Layer 4/TCP resource.
- `nginx`: renders a standard `Ingress` with `nginx.ingress.kubernetes.io/ssl-passthrough: "true"`. This requires the NGINX Ingress Controller to be started with `--enable-ssl-passthrough`.
- `loadBalancer`: uses the Kubernetes `Service` type `LoadBalancer`. This is useful on AWS or other clouds when you already run a load balancer controller and want to pass controller-specific annotations or `loadBalancerClass` values.
- `gateway-api`: renders a Gateway API `TLSRoute` or `TCPRoute`. It is not an `ingress` provider: it has its own `*.gatewayAPI` values and its own templates, so `ingress` and `gatewayAPI` can be on together or apart.

The chart does not force any controller. Leave `concierge.ingress.enabled=false`, `supervisor.ingress.enabled=false` and the `*.gatewayAPI.enabled` values off if you prefer to expose Pinniped only through a `LoadBalancer`, `NodePort`, or another TCP proxy.

### LoadBalancer notes

For cloud-native exposure, use the `service.*.loadBalancer.*` values.

- `supervisor.service.public.loadBalancer.annotations` lets you pass AWS Load Balancer Controller annotations such as `service.beta.kubernetes.io/aws-load-balancer-scheme`.
- `supervisor.service.public.loadBalancer.loadBalancerClass` can be used with implementations like AWS NLB.
- `concierge.service.proxy.*` provides the same controls when the Concierge impersonation proxy is exposed directly.

### Gateway API notes

Gateway API is set under `<component>.gatewayAPI`, next to `ingress` and not inside it. Set `*.gatewayAPI.enabled=true` and at least one `parentRefs` entry, on the component or once for both under `global.gatewayAPI`.

```yaml
global:
  domain: example.com
  gatewayAPI:
    enabled: true
    parentRefs:
      - name: main-gateway
        sectionName: tls
```

- Use `routeKind: TLSRoute` when your Gateway implementation supports TLS passthrough with SNI matching. The route matches the hostname: `gatewayAPI.hostnames`, then `gatewayAPI.hostname`, then the `ingress` hostname (`<hostPrefix>.<global.domain>` when unset).
- Use `routeKind: TCPRoute` when you want pure TCP forwarding and your Gateway implementation does not support `TLSRoute`. A `TCPRoute` has no hostnames.
- `*.gatewayAPI.apiVersion` is empty by default and follows the kind: `gateway.networking.k8s.io/v1` for a `TLSRoute` and `gateway.networking.k8s.io/v1alpha2` for a `TCPRoute`. Which versions are served depends on the Gateway API release and channel you installed (`TLSRoute` is `v1` in the standard channel from Gateway API 1.5, `TCPRoute` is in the experimental channel until `v1`), so set it when your CRDs serve another one. `kubectl get crd tlsroutes.gateway.networking.k8s.io -o jsonpath='{.spec.versions[*].name}'` lists them.
- The route has its own backend, `*.gatewayAPI.service.{name,port}`. Empty uses the same Service the ingress would, and the Supervisor's `ClusterIP` Service is created for it, so `*.ingress.enabled` can stay off.
- Route annotations are `*.gatewayAPI.annotations`. `*.ingress.annotations` apply only to the ingress resources.
- The Gateway terminates nothing: its listener must pass TLS through to the Pinniped pods.

Moving from 0.1.x: `*.ingress.provider=gateway-api` and `*.ingress.gatewayAPI.*` now fail the render with a message that names the new place. Move the keys to `*.gatewayAPI.*` and leave `ingress.provider` at `traefik` or `nginx`.

## TLS certificate options

Pinniped still needs certificates even when TCP passthrough is used, because TLS terminates inside the Pinniped pods.

This chart provides optional cert-manager integration, but does not require cert-manager as a chart dependency.

- Set `supervisor.tls.certManager.enabled=true` to create a `Certificate` for the Supervisor `defaultTLSCertificateSecret`.
- Set `concierge.tls.certManager.enabled=true` to create a `Certificate` for the Concierge impersonation proxy TLS secret.
- Set `*.tls.certManager.createSelfSignedIssuer=true` to let the chart create a simple self-signed `Issuer` in the component namespace.

If you already have your own issuer, set `*.tls.certManager.issuerRef.*` and keep `createSelfSignedIssuer=false`.

The Certificate `dnsNames` default to the component's ingress hostname, so you rarely set them. To set them, any of these works:

```bash
--set 'supervisor.tls.certManager.certificate.dnsNames[0]=sso.example.com'
--set 'supervisor.tls.certManager.certificate.dnsNames={sso.example.com,sso.example.org}'
```

```yaml
supervisor:
  tls:
    certManager:
      certificate:
        dnsNames: [sso.example.com]
```

A single name, `[sso.example.com]`, `["sso.example.com"]` and `sso.example.com,sso.example.org` are read as lists too. Helm's `--set` does not turn `[...]` into a list, and Argo CD passes a parameter as you typed it, so these reach the chart as plain text. Brackets, quotes and spaces cannot be part of a host name, so they are dropped. Anything that is not a name or a list fails with the key in the message.

## Example

```yaml
supervisor:
  ingress:
    enabled: true
    provider: traefik
    hostname: supervisor.example.com
  tls:
    certManager:
      enabled: true
      createSelfSignedIssuer: true

concierge:
  ingress:
    enabled: true
    provider: nginx
    className: nginx
    hostname: concierge.example.com
  tls:
    certManager:
      enabled: true
      createSelfSignedIssuer: true
```

## Authentication configuration

After deploying the Supervisor, configure it as an OIDC issuer by creating a `FederationDomain` and connecting one or more identity providers. Then create a `JWTAuthenticator` on each downstream Concierge to trust those tokens.

### FederationDomain

The `FederationDomain` is the public OIDC issuer URL published by the Supervisor. Its `issuer` field must be a fully qualified HTTPS URL reachable by end-users and by Concierge clusters.

```yaml
supervisor:
  federationDomain:
    create: true
    issuer: https://supervisor.example.com
    # tlsSecretName defaults to the cert-manager-managed secret when
    # supervisor.tls.certManager.enabled=true. Override only when needed.
    tlsSecretName: ""
```

### Identity providers

Enable exactly the IDPs your environment needs. Enabled IDPs are automatically registered in the FederationDomain's `identityProviders` list.

#### Dex (OIDC)

```yaml
supervisor:
  identityProviders:
    dex:
      create: true
      name: dex
      displayName: "Dex"
      issuer: https://dex.example.com
      # certificateAuthorityData: "<base64-pem>"  # omit if Dex uses a public CA
      additionalScopes: [offline_access, groups, email]
      allowPasswordGrant: false
      usernameClaim: email
      groupsClaim: groups
      createClientSecret: true
      clientID: pinniped
      clientSecret: "<dex-client-secret>"
```

#### GitHub

```yaml
supervisor:
  identityProviders:
    github:
      create: true
      name: github
      displayName: "GitHub"
      organizationPolicy: OnlyUsersFromAllowedOrganizations
      allowedOrganizations:
        - my-org
      usernameClaim: "login:id"
      groupsClaim: slug
      createClientSecret: true
      clientID: "<github-app-client-id>"
      clientSecret: "<github-app-client-secret>"
```

Set `host` and `certificateAuthorityData` when using GitHub Enterprise Server instead of `github.com`.

#### LDAP

```yaml
supervisor:
  identityProviders:
    ldap:
      create: true
      name: openldap
      displayName: "LDAP"
      host: "ldap.example.com:636"
      # certificateAuthorityData: "<base64-pem>"  # omit if using a public CA
      userSearch:
        base: "ou=users,dc=example,dc=com"
        filter: "&(objectClass=inetOrgPerson)(uid={})"
        usernameAttribute: uid
        uidAttribute: uidNumber
      groupSearch:
        base: "ou=groups,dc=example,dc=com"
        filter: "&(objectClass=groupOfNames)(member={})"
        groupNameAttribute: cn
      createBindSecret: true
      bindUsername: "cn=admin,dc=example,dc=com"
      bindPassword: "<bind-password>"
```

### JWTAuthenticator (Concierge)

Create one `JWTAuthenticator` per downstream Concierge cluster. Its `issuer` must exactly match `supervisor.federationDomain.issuer`.

```yaml
concierge:
  jwtAuthenticator:
    create: true
    name: supervisor-jwt-authenticator
    issuer: https://supervisor.example.com
    audience: my-cluster          # unique identifier for this cluster
    # certificateAuthorityData: "<base64-pem>"
    # Omit certificateAuthorityData when the Supervisor uses a publicly trusted CA.
    # For dynamic rotation, reference a Secret or ConfigMap instead:
    # certificateAuthorityDataSource:
    #   kind: Secret
    #   name: pinniped-supervisor-default-tls-certificate
    #   key: ca.crt
```

> **TLS trust note**: When `supervisor.tls.certManager.enabled=true` with a public CA issuer (e.g. Let's Encrypt), you can omit `certificateAuthorityData` entirely because the CA is already trusted by default. Only set it when using a private or self-signed CA.

Gateway API example:

```yaml
supervisor:
	ingress:
		hostname: supervisor.example.com
	gatewayAPI:
		enabled: true
		routeKind: TLSRoute
		parentRefs:
			- name: main-gateway
				sectionName: https
```

AWS/NLB-style load balancer example:

```yaml
supervisor:
	service:
		public:
			loadBalancer:
				enabled: true
				loadBalancerClass: service.k8s.aws/nlb
				annotations:
					service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing
```

## Pinniped Note

Explore more about Pinniped at https://pinniped.dev/ and the official architecture at https://pinniped.dev/docs/background/architecture/ to understand how the Concierge and Supervisor components work together to provide secure Kubernetes authentication.

Pinniped is a open-source project under the VMware and it has many installation options. This chart is customized base on my experience, so you can find the more options at
1. The official documentation: https://pinniped.dev/docs/howto/install-concierge/ and https://pinniped.dev/docs/howto/install-supervisor/
2. Bitnami's chart: https://artifacthub.io/packages/helm/bitnami/pinniped

By default, this chart will not create and expose services and ingress for both Concierge and Supervisor, and sometime it look noisy if you don't cover the documentation well, so that is why I share this chart to make it easier for you to get started with Pinniped and customize it for your needs. With more configuration options for

1. Setup Service and Ingress with different providers and patterns, such as Traefik, NGINX, Gateway API, and LoadBalancer at Layer 4/TCP with SSL Passthrough
2. Setup TLS certificates with cert-manager integration, including self-signed issuers for local development and testing. Because Pinniped requires end-to-end TLS, so you can use cert-manager to automate certificate management for both the Supervisor and Concierge components.
3. Support you modify configuration for both Supervisor and Concierge components seperately, it help you prevent errors for mismatch in configuration for couple of situations, such as

The Concierge impersonation proxy is exposed as a `ClusterIP` Service by default, with no cloud annotations. That works on any cluster without a load balancer controller. Put your own ingress, Gateway API route or TCP proxy in front of it and tell clients where it is with `externalEndpoint`. Left empty, Pinniped advertises the Service's cluster DNS name, which only works from inside the cluster.

Two settings choose the Service type, and they are not the same thing:

- `concierge.credentialIssuer.impersonationProxy.service.type` (`ClusterIP`, `LoadBalancer` or `None`) is what the Concierge creates for itself from the `CredentialIssuer`: `...-impersonation-proxy-cluster-ip` or `...-impersonation-proxy-load-balancer`. Set it to `LoadBalancer`, with `service.annotations` and `service.loadBalancerIP`, to have Pinniped create a cloud load balancer. The annotations apply only to a `LoadBalancer`. See the [Pinniped API](https://github.com/vmware/pinniped/tree/main/generated/latest#impersonationproxyservicetype-string).
- `concierge.service.proxy.*` is a Service created by this chart for the same pods, and it is the backend `concierge.ingress` and `concierge.gatewayAPI` point at. It defaults to `ClusterIP` too.

Use `mode: enabled` when your cluster has a `kube-controller-manager` Pinniped can find and you still want the proxy, and `auto` (the default) to let Pinniped turn it on only for clusters without one, such as managed Kubernetes.

```yaml
  # -- CredentialIssuer bootstrap resource for Concierge impersonation support.
  credentialIssuer:
    create: true
    impersonationProxy:
      mode: enabled
      externalEndpoint: "concierge-endpoint.example.com"
      service:
        type: ClusterIP
```

## Installing the CRDs

The chart ships nine Pinniped CRDs (`FederationDomain`, `OIDCClient`, the identity providers, `JWTAuthenticator`, `WebhookAuthenticator`, `CredentialIssuer`) in `crds/`, and each only once. CRDs are cluster-wide, so what matters is who owns them on a cluster: install them from exactly one place, and tell every other install to leave them alone.

| Situation | Helm | Argo CD |
| --- | --- | --- |
| **First install on a cluster.** The chart installs the CRDs. | `helm install pinniped wxops/pinniped` | Leave `skipCrds` unset. |
| **Another release on a cluster that already has the CRDs.** | The same command works, Helm logs `CRD … is already present. Skipping.` Add `--skip-crds` to not touch them at all. | Set `helm.skipCrds: true` on every Application except the one that owns the CRDs. |
| **CRDs managed somewhere else** (your own Application, `kubectl`, a GitOps repo). | `--skip-crds` | `helm.skipCrds: true` |
| **Upgrading the chart.** | Helm never upgrades `crds/`. Apply them yourself, see below. | The Application that owns the CRDs re-applies them on every sync. |

Argo CD renders the chart with `helm template --include-crds`, so by default it manages the CRDs together with the rest. Exactly one Application should do that. If two Applications render the same CRDs, Argo CD reports them as shared resources and pruning one Application can delete CRDs the other still needs:

```yaml
# The Application that owns the CRDs: nothing to set.
# Every other Application that installs this chart:
spec:
  source:
    repoURL: https://charts.wxops.cloud
    chart: pinniped
    targetRevision: 0.2.0
    helm:
      skipCrds: true
```

**Upgrading the CRDs with Helm.** Helm only installs `crds/` on the first install and never changes them afterwards, so apply them from the chart version you are upgrading to before you run `helm upgrade`:

```bash
helm show crds wxops/pinniped --version <new version> | kubectl apply --server-side -f -
helm upgrade pinniped wxops/pinniped --version <new version>
```

**Uninstalling.** `helm uninstall` leaves the CRDs in place, and with them your `FederationDomain`, `JWTAuthenticator` and other resources. Deleting the Argo CD Application that owns the CRDs with the default cascading delete removes the CRDs too, and every Pinniped resource with them, so use a non-cascading delete there. Delete the CRDs by hand only when you really want Pinniped gone from the cluster.

### Upgrading from 0.1.x

Versions before 0.2.0 also had an `installCRDs` value that rendered the same CRDs a second time from `templates/`. That is what failed with `exists and cannot be imported into the current release` or created the CRDs twice in Argo CD. The value and the template are gone, the CRDs now come from `crds/` only, and a leftover `installCRDs` in your values is ignored.

If you installed with Helm using `installCRDs=true` **and** `--skip-crds`, the release owns the CRDs, and Helm deletes anything a release rendered before but no longer renders. Mark the CRDs to be kept before upgrading, or the upgrade deletes them and every Pinniped resource with them:

```bash
helm get manifest pinniped -n pinniped | grep -c '^kind: CustomResourceDefinition'   # more than 0 means the release owns them
kubectl get crd -o name | grep 'pinniped.dev' | xargs -I{} kubectl annotate {} helm.sh/resource-policy=keep --overwrite
```

Argo CD users are not affected, Argo CD keeps rendering the CRDs from `crds/`. If you set `skipCrds: true` before, nothing changes.

## Installing the Chart

To install the chart with the release name `pinniped`, CRDs included:

```bash
helm repo add wxops https://charts.wxops.cloud
helm install pinniped wxops/pinniped
```

When the CRDs are already on the cluster or managed elsewhere, skip them, see [Installing the CRDs](#installing-the-crds):

```bash
helm install pinniped wxops/pinniped --skip-crds
```

For local rendering/testing:

```bash
helm template pinniped . -f values.yaml
helm lint .
```

## Uninstalling the Chart

```bash
helm uninstall pinniped
```

The CRDs are kept, see [Installing the CRDs](#installing-the-crds).

## Also preference

- [Pinniped Documentation](https://pinniped.dev/docs/)
- [Using Pinniped for authentication against Talos-based Kubernetes clusters](https://dickingwithdocker.com/posts/pinniped-authentication-against-talos-clusters/)
- [OpenUnison - Deploying The Authentication Portal](https://openunison.github.io/deployauth/)
- [Pinniped: A Unified Framework for User Authentication to Kubernetes Cluster- Mo Khan & Anjali Telang](https://www.youtube.com/watch?v=2fI_XOGEoIU)
- [Pinniped - Concierge with Supervisor Locally](https://pinniped.dev/docs/tutorials/local-concierge-and-supervisor-demo/)

## Alternative solutions

- [Kubelogin](https://github.com/int128/kubelogin): kubectl plugin for Kubernetes OpenID Connect authentication (kubectl oidc-login)
- [kube-oidc-proxy](https://github.com/jetstack/kube-oidc-proxy/tree/master): Reverse proxy to authenticate to managed Kubernetes API servers via OIDC.
- [OpenUnison](https://openunison.github.io/): OpenUnison provides SSO and authentication for your Kubernetes clusters, no matter where they run or how your users need to authenticate.
- [gangway](https://github.com/vmware-archive/gangway): An application that can be used to easily enable authentication flows via OIDC for a kubernetes cluster.
- [paralus](https://github.com/paralus/paralus): All-in-one Kubernetes access manager. User-level credentials, RBAC, SSO, audit logs.
- [dex-k8s-authenticator](https://github.com/mintel/dex-k8s-authenticator): A Kubernetes Dex Client Authenticator

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| Xeus Nguyen | <xeusnguyen@gmail.com> | <https://wiki.xeusnguyen.xyz> |

## Source Code

* <https://github.com/vmware/pinniped>

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| commonLabels | object | `{}` | Common labels applied to all rendered resources. |
| concierge | object | `{"config":{"allowedCiphersForTLSOneDotTwo":[],"apiGroupSuffix":"pinniped.dev","apiServingCertificateDurationSeconds":2592000,"apiServingCertificateRenewBeforeSeconds":2160000,"audit":{"logUsernamesAndGroups":"disabled"},"discoveryURL":"","httpsProxy":"","kubeCertAgentImage":"","kubeCertAgentPriorityClassName":"","logLevel":"","noProxy":"$(KUBERNETES_SERVICE_HOST),169.254.169.254,127.0.0.1,localhost,.svc,.cluster.local"},"containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true,"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"credentialIssuer":{"create":true,"impersonationProxy":{"externalEndpoint":"","mode":"auto","service":{"annotations":{},"loadBalancerIP":"","type":"ClusterIP"}}},"customLabels":{},"enabled":true,"gatewayAPI":{"annotations":{},"apiVersion":"","enabled":null,"hostname":"","hostnames":[],"parentRefs":[],"routeKind":"TLSRoute","routeName":"","service":{"name":"","port":443}},"image":{"digest":"","pullPolicy":"IfNotPresent","repository":"ghcr.io/vmware/pinniped/pinniped-server","tag":""},"imagePullSecret":{"create":false,"dockerconfigjson":"","name":"image-pull-secret"},"ingress":{"annotations":{},"enabled":null,"hostPrefix":"concierge","hostname":"","nginx":{"backendProtocol":"HTTPS","path":"/","pathType":"Prefix","sslPassthrough":"true","tlsSecretName":""},"provider":"","service":{"name":"","port":443},"traefik":{"entryPoints":["websecure"],"match":"","tlsPassthrough":true,"tlsSecretName":""}},"jwtAuthenticator":{"audience":"","certificateAuthorityData":"","certificateAuthorityDataSource":{"key":"","kind":"","name":""},"create":false,"issuer":"","name":"supervisor-jwt-authenticator"},"nameOverride":"","podSecurityContext":{"runAsGroup":65532,"runAsUser":65532},"replicaCount":1,"resources":{"limits":{"cpu":"100m","memory":"128Mi"},"requests":{"cpu":"100m","memory":"128Mi"}},"service":{"api":{"port":443,"targetPort":10250},"proxy":{"annotations":{},"enabled":true,"externalTrafficPolicy":"","loadBalancerClass":"","loadBalancerIP":"","loadBalancerSourceRanges":[],"port":443,"targetPort":8444,"type":"ClusterIP"}},"tls":{"certManager":{"certificate":{"commonName":"","dnsNames":[],"duration":"","enabled":true,"privateKey":{"algorithm":"RSA","size":2048},"renewBefore":"","secretName":""},"createSelfSignedIssuer":false,"enabled":null,"issuerRef":{"group":"","kind":"","name":""}},"secretNames":{"api":"","impersonationProxy":""}}}` | Pinniped Concierge component configuration. |
| concierge.config | object | `{"allowedCiphersForTLSOneDotTwo":[],"apiGroupSuffix":"pinniped.dev","apiServingCertificateDurationSeconds":2592000,"apiServingCertificateRenewBeforeSeconds":2160000,"audit":{"logUsernamesAndGroups":"disabled"},"discoveryURL":"","httpsProxy":"","kubeCertAgentImage":"","kubeCertAgentPriorityClassName":"","logLevel":"","noProxy":"$(KUBERNETES_SERVICE_HOST),169.254.169.254,127.0.0.1,localhost,.svc,.cluster.local"}` | Concierge static configuration rendered into the Pinniped config file. |
| concierge.config.allowedCiphersForTLSOneDotTwo | list | `[]` | Allowed TLS 1.2 cipher suites for Concierge. Empty uses Pinniped defaults. |
| concierge.config.apiGroupSuffix | string | `"pinniped.dev"` | API group suffix for Concierge APIs. |
| concierge.config.apiServingCertificateDurationSeconds | int | `2592000` | Lifetime of the Concierge API serving certificate in seconds. |
| concierge.config.apiServingCertificateRenewBeforeSeconds | int | `2160000` | Renew-before interval of the Concierge API serving certificate in seconds. |
| concierge.config.audit | object | `{"logUsernamesAndGroups":"disabled"}` | Concierge audit logging configuration. |
| concierge.config.audit.logUsernamesAndGroups | string | `"disabled"` | Include usernames and groups in Concierge audit logs. |
| concierge.config.discoveryURL | string | `""` | Override the Kubernetes discovery URL published by Concierge. |
| concierge.config.httpsProxy | string | `""` | HTTPS proxy used by Concierge for outbound requests. |
| concierge.config.kubeCertAgentImage | string | `""` | Override the kube-cert-agent image used by Concierge. |
| concierge.config.kubeCertAgentPriorityClassName | string | `""` | PriorityClass name assigned to kube-cert-agent pods. |
| concierge.config.logLevel | string | `""` | Concierge log level. Leave empty for Pinniped defaults. |
| concierge.config.noProxy | string | `"$(KUBERNETES_SERVICE_HOST),169.254.169.254,127.0.0.1,localhost,.svc,.cluster.local"` | NO_PROXY list used by Concierge for outbound requests. |
| concierge.containerSecurityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true,"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}}` | Container-level security context for the Concierge container. |
| concierge.containerSecurityContext.allowPrivilegeEscalation | bool | `false` | Disable privilege escalation in the Concierge container. |
| concierge.containerSecurityContext.capabilities | object | `{"drop":["ALL"]}` | Linux capabilities configuration for the Concierge container. |
| concierge.containerSecurityContext.capabilities.drop | list | `["ALL"]` | Capabilities dropped from the Concierge container. |
| concierge.containerSecurityContext.readOnlyRootFilesystem | bool | `true` | Mount the root filesystem as read-only. |
| concierge.containerSecurityContext.runAsNonRoot | bool | `true` | Require the Concierge container to run as a non-root user. |
| concierge.containerSecurityContext.seccompProfile | object | `{"type":"RuntimeDefault"}` | Seccomp profile applied to the Concierge container. |
| concierge.containerSecurityContext.seccompProfile.type | string | `"RuntimeDefault"` | Seccomp profile type. |
| concierge.credentialIssuer | object | `{"create":true,"impersonationProxy":{"externalEndpoint":"","mode":"auto","service":{"annotations":{},"loadBalancerIP":"","type":"ClusterIP"}}}` | CredentialIssuer bootstrap resource for Concierge impersonation support. |
| concierge.credentialIssuer.create | bool | `true` | Create the default `CredentialIssuer` resource. |
| concierge.credentialIssuer.impersonationProxy | object | `{"externalEndpoint":"","mode":"auto","service":{"annotations":{},"loadBalancerIP":"","type":"ClusterIP"}}` | CredentialIssuer impersonation proxy configuration. |
| concierge.credentialIssuer.impersonationProxy.externalEndpoint | string | `""` | External endpoint advertised by the impersonation proxy. |
| concierge.credentialIssuer.impersonationProxy.mode | string | `"auto"` | Impersonation proxy mode (`auto`, `enabled`, or `disabled`). |
| concierge.credentialIssuer.impersonationProxy.service | object | `{"annotations":{},"loadBalancerIP":"","type":"ClusterIP"}` | Service settings published in the CredentialIssuer status. |
| concierge.credentialIssuer.impersonationProxy.service.annotations | object | `{}` | Service annotations published for the impersonation proxy endpoint. Only used with `type: LoadBalancer`, e.g. the AWS `service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout: "4000"`. |
| concierge.credentialIssuer.impersonationProxy.service.loadBalancerIP | string | `""` | Static load balancer IP reported for the impersonation proxy endpoint. |
| concierge.credentialIssuer.impersonationProxy.service.type | string | `"ClusterIP"` | Service type reported for the impersonation proxy endpoint. (`ClusterIP` or `LoadBalancer` or `None`). Ref: https://github.com/vmware/pinniped/tree/main/generated/latest#impersonationproxyservicetype-string |
| concierge.customLabels | object | `{}` | Additional labels applied only to Concierge resources. |
| concierge.enabled | bool | `true` | Enable Concierge resources. |
| concierge.gatewayAPI | object | `{"annotations":{},"apiVersion":"","enabled":null,"hostname":"","hostnames":[],"parentRefs":[],"routeKind":"TLSRoute","routeName":"","service":{"name":"","port":443}}` | Gateway API route for Concierge. It is separate from `ingress`: enable one, the other, or both. The route is a `TLSRoute` (SNI passthrough) or a `TCPRoute`, so the Gateway needs a TLS passthrough or TCP listener. |
| concierge.gatewayAPI.annotations | object | `{}` | Additional annotations on the route. |
| concierge.gatewayAPI.apiVersion | string | `""` | API version of the route. Empty picks one for the kind: `gateway.networking.k8s.io/v1` for a `TLSRoute`, `gateway.networking.k8s.io/v1alpha2` for a `TCPRoute`. Set it to match the Gateway API CRDs you installed. |
| concierge.gatewayAPI.enabled | string | `nil` | Render the Gateway API route for Concierge. `null` inherits `global.gatewayAPI.enabled`. |
| concierge.gatewayAPI.hostname | string | `""` | Hostname of a `TLSRoute`. Empty uses the `ingress` hostname, which is `<ingress.hostPrefix>.<global.domain>` when unset. |
| concierge.gatewayAPI.hostnames | list | `[]` | Several hostnames for a `TLSRoute`. Wins over `hostname`. |
| concierge.gatewayAPI.parentRefs | list | `[]` | Gateways the route attaches to. Empty inherits `global.gatewayAPI.parentRefs`. One is required. |
| concierge.gatewayAPI.routeKind | string | `"TLSRoute"` | Route kind: `TLSRoute` (matches the SNI hostnames) or `TCPRoute` (plain TCP, no hostnames). |
| concierge.gatewayAPI.routeName | string | `""` | Override the generated route name. |
| concierge.gatewayAPI.service | object | `{"name":"","port":443}` | Backend of the route. It does not follow `ingress.service`. |
| concierge.gatewayAPI.service.name | string | `""` | Explicit backend service name. Empty uses the same service the ingress would. |
| concierge.gatewayAPI.service.port | int | `443` | Backend service port. |
| concierge.image | object | `{"digest":"","pullPolicy":"IfNotPresent","repository":"ghcr.io/vmware/pinniped/pinniped-server","tag":""}` | Concierge container image settings. |
| concierge.image.digest | string | `""` | Concierge image digest. Takes precedence over `tag` when set. |
| concierge.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the Concierge container. |
| concierge.image.repository | string | `"ghcr.io/vmware/pinniped/pinniped-server"` | Concierge image repository. |
| concierge.image.tag | string | `""` | Concierge image tag. Defaults to the chart appVersion when empty. |
| concierge.imagePullSecret | object | `{"create":false,"dockerconfigjson":"","name":"image-pull-secret"}` | Optional image pull secret configuration for private registries. |
| concierge.imagePullSecret.create | bool | `false` | Create a dockerconfigjson secret for pulling the Pinniped image. |
| concierge.imagePullSecret.dockerconfigjson | string | `""` | Base64-encoded `.dockerconfigjson` payload used when `create=true`. |
| concierge.imagePullSecret.name | string | `"image-pull-secret"` | Name of the image pull secret. |
| concierge.ingress | object | `{"annotations":{},"enabled":null,"hostPrefix":"concierge","hostname":"","nginx":{"backendProtocol":"HTTPS","path":"/","pathType":"Prefix","sslPassthrough":"true","tlsSecretName":""},"provider":"","service":{"name":"","port":443},"traefik":{"entryPoints":["websecure"],"match":"","tlsPassthrough":true,"tlsSecretName":""}}` | Concierge ingress settings for Traefik or NGINX passthrough. |
| concierge.ingress.annotations | object | `{}` | Additional annotations applied to the Concierge ingress resources. |
| concierge.ingress.enabled | string | `nil` | Enable ingress exposure (Traefik or NGINX) for Concierge. `null` inherits `global.ingress.enabled`. |
| concierge.ingress.hostPrefix | string | `"concierge"` | First label of the hostname built from `global.domain`. |
| concierge.ingress.hostname | string | `""` | Primary hostname used by Concierge passthrough exposure. Empty becomes `<hostPrefix>.<global.domain>` when `global.domain` is set. |
| concierge.ingress.nginx | object | `{"backendProtocol":"HTTPS","path":"/","pathType":"Prefix","sslPassthrough":"true","tlsSecretName":""}` | NGINX SSL passthrough ingress settings. |
| concierge.ingress.nginx.backendProtocol | string | `"HTTPS"` | Value for the `nginx.ingress.kubernetes.io/backend-protocol` annotation. |
| concierge.ingress.nginx.path | string | `"/"` | HTTP path used by the compatibility ingress resource. |
| concierge.ingress.nginx.pathType | string | `"Prefix"` | Path type used by the compatibility ingress resource. |
| concierge.ingress.nginx.sslPassthrough | string | `"true"` | Value for the `nginx.ingress.kubernetes.io/ssl-passthrough` annotation. |
| concierge.ingress.nginx.tlsSecretName | string | `""` | TLS secret name for SSL. Typically the cert-manager-managed secret name. |
| concierge.ingress.provider | string | `""` | Exposure provider (`traefik` or `nginx`). Empty inherits `global.ingress.provider`. |
| concierge.ingress.service | object | `{"name":"","port":443}` | Backend service override used by the ingress. |
| concierge.ingress.service.name | string | `""` | Explicit service name used as the ingress backend. |
| concierge.ingress.service.port | int | `443` | Service port used as the ingress backend. |
| concierge.ingress.traefik | object | `{"entryPoints":["websecure"],"match":"","tlsPassthrough":true,"tlsSecretName":""}` | Traefik `IngressRouteTCP` settings. |
| concierge.ingress.traefik.entryPoints | list | `["websecure"]` | EntryPoints attached to the Traefik TCP route. |
| concierge.ingress.traefik.match | string | `""` | Optional custom Traefik TCP match expression. Defaults to `HostSNI(hostname)`. |
| concierge.ingress.traefik.tlsPassthrough | bool | `true` | Enable TLS passthrough for Traefik TCP routing. |
| concierge.ingress.traefik.tlsSecretName | string | `""` | TLS secret name for SSL. Typically the cert-manager-managed secret name. |
| concierge.jwtAuthenticator | object | `{"audience":"","certificateAuthorityData":"","certificateAuthorityDataSource":{"key":"","kind":"","name":""},"create":false,"issuer":"","name":"supervisor-jwt-authenticator"}` | JWTAuthenticator that validates tokens issued by a Pinniped Supervisor FederationDomain. |
| concierge.jwtAuthenticator.audience | string | `""` | Unique audience identifier for this cluster. |
| concierge.jwtAuthenticator.certificateAuthorityData | string | `""` | Base64-encoded PEM CA bundle for validating the Supervisor TLS certificate. Leave empty when using a publicly trusted CA. |
| concierge.jwtAuthenticator.certificateAuthorityDataSource | object | `{"key":"","kind":"","name":""}` | Dynamic CA bundle source watched by Pinniped for rotation (alternative to `certificateAuthorityData`). |
| concierge.jwtAuthenticator.certificateAuthorityDataSource.key | string | `""` | Key within the resource that contains the PEM CA bundle. |
| concierge.jwtAuthenticator.certificateAuthorityDataSource.kind | string | `""` | Kind of the source resource: `Secret` or `ConfigMap`. |
| concierge.jwtAuthenticator.certificateAuthorityDataSource.name | string | `""` | Name of the Secret or ConfigMap containing the CA bundle. |
| concierge.jwtAuthenticator.create | bool | `false` | Create a JWTAuthenticator resource on this cluster's Concierge. |
| concierge.jwtAuthenticator.issuer | string | `""` | Issuer URL of the Supervisor FederationDomain. Must exactly match `supervisor.federationDomain.issuer`. |
| concierge.jwtAuthenticator.name | string | `"supervisor-jwt-authenticator"` | Name of the JWTAuthenticator resource. |
| concierge.nameOverride | string | `""` | Override the default Concierge resource name prefix. |
| concierge.podSecurityContext | object | `{"runAsGroup":65532,"runAsUser":65532}` | Pod-level security context for Concierge pods. |
| concierge.podSecurityContext.runAsGroup | int | `65532` | GID used to run the Concierge pod. |
| concierge.podSecurityContext.runAsUser | int | `65532` | UID used to run the Concierge pod. |
| concierge.replicaCount | int | `1` | Number of Concierge replicas. |
| concierge.resources | object | `{"limits":{"cpu":"100m","memory":"128Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits for the Concierge container. |
| concierge.resources.limits | object | `{"cpu":"100m","memory":"128Mi"}` | Resource limits for the Concierge container. |
| concierge.resources.limits.cpu | string | `"100m"` | CPU limit for the Concierge container. |
| concierge.resources.limits.memory | string | `"128Mi"` | Memory limit for the Concierge container. |
| concierge.resources.requests | object | `{"cpu":"100m","memory":"128Mi"}` | Resource requests for the Concierge container. |
| concierge.resources.requests.cpu | string | `"100m"` | Requested CPU for the Concierge container. |
| concierge.resources.requests.memory | string | `"128Mi"` | Requested memory for the Concierge container. |
| concierge.service | object | `{"api":{"port":443,"targetPort":10250},"proxy":{"annotations":{},"enabled":true,"externalTrafficPolicy":"","loadBalancerClass":"","loadBalancerIP":"","loadBalancerSourceRanges":[],"port":443,"targetPort":8444,"type":"ClusterIP"}}` | Service settings for Concierge internal and impersonation proxy traffic. |
| concierge.service.api | object | `{"port":443,"targetPort":10250}` | Service exposing the aggregated Concierge API. |
| concierge.service.api.port | int | `443` | External service port for the Concierge API service. |
| concierge.service.api.targetPort | int | `10250` | Container target port for the Concierge API service. |
| concierge.service.proxy | object | `{"annotations":{},"enabled":true,"externalTrafficPolicy":"","loadBalancerClass":"","loadBalancerIP":"","loadBalancerSourceRanges":[],"port":443,"targetPort":8444,"type":"ClusterIP"}` | Service exposing the Concierge impersonation proxy. |
| concierge.service.proxy.annotations | object | `{}` | Additional annotations for the impersonation proxy service. |
| concierge.service.proxy.enabled | bool | `true` | Create the impersonation proxy service. |
| concierge.service.proxy.externalTrafficPolicy | string | `""` | Optional external traffic policy for the impersonation proxy service. |
| concierge.service.proxy.loadBalancerClass | string | `""` | Optional `loadBalancerClass` for the impersonation proxy service. |
| concierge.service.proxy.loadBalancerIP | string | `""` | Static load balancer IP for the impersonation proxy service. |
| concierge.service.proxy.loadBalancerSourceRanges | list | `[]` | Optional source ranges allowed to reach the impersonation proxy load balancer. |
| concierge.service.proxy.port | int | `443` | External service port for the impersonation proxy. |
| concierge.service.proxy.targetPort | int | `8444` | Container target port for the impersonation proxy. |
| concierge.service.proxy.type | string | `"ClusterIP"` | Kubernetes service type for the impersonation proxy. |
| concierge.tls | object | `{"certManager":{"certificate":{"commonName":"","dnsNames":[],"duration":"","enabled":true,"privateKey":{"algorithm":"RSA","size":2048},"renewBefore":"","secretName":""},"createSelfSignedIssuer":false,"enabled":null,"issuerRef":{"group":"","kind":"","name":""}},"secretNames":{"api":"","impersonationProxy":""}}` | TLS secret and optional cert-manager configuration for Concierge. |
| concierge.tls.certManager | object | `{"certificate":{"commonName":"","dnsNames":[],"duration":"","enabled":true,"privateKey":{"algorithm":"RSA","size":2048},"renewBefore":"","secretName":""},"createSelfSignedIssuer":false,"enabled":null,"issuerRef":{"group":"","kind":"","name":""}}` | Optional cert-manager integration for Concierge certificates. |
| concierge.tls.certManager.certificate | object | `{"commonName":"","dnsNames":[],"duration":"","enabled":true,"privateKey":{"algorithm":"RSA","size":2048},"renewBefore":"","secretName":""}` | cert-manager certificate options for Concierge. |
| concierge.tls.certManager.certificate.commonName | string | `""` | Optional common name used in the Concierge certificate. |
| concierge.tls.certManager.certificate.dnsNames | list | `[]` | DNS names included in the Concierge certificate. |
| concierge.tls.certManager.certificate.duration | string | `""` | Optional certificate duration passed to cert-manager. |
| concierge.tls.certManager.certificate.enabled | bool | `true` | Create a cert-manager `Certificate` for Concierge. |
| concierge.tls.certManager.certificate.privateKey | object | `{"algorithm":"RSA","size":2048}` | Private key settings used by cert-manager. |
| concierge.tls.certManager.certificate.privateKey.algorithm | string | `"RSA"` | Private key algorithm for the Concierge certificate. |
| concierge.tls.certManager.certificate.privateKey.size | int | `2048` | Private key size for the Concierge certificate. |
| concierge.tls.certManager.certificate.renewBefore | string | `""` | Optional renew-before duration passed to cert-manager. |
| concierge.tls.certManager.certificate.secretName | string | `""` | Override the secret name written by the cert-manager `Certificate`. |
| concierge.tls.certManager.createSelfSignedIssuer | bool | `false` | Create a simple self-signed `Issuer` in the Concierge namespace. |
| concierge.tls.certManager.enabled | string | `nil` | Enable cert-manager resources for Concierge. `null` inherits `global.certManager.enabled`. |
| concierge.tls.certManager.issuerRef | object | `{"group":"","kind":"","name":""}` | cert-manager issuer reference used by the Concierge certificate. |
| concierge.tls.certManager.issuerRef.group | string | `""` | API group of the cert-manager issuer or clusterissuer resource. Empty inherits `global.certManager.issuerRef.group`. |
| concierge.tls.certManager.issuerRef.kind | string | `""` | Kind of the cert-manager issuer or clusterissuer resource. Empty inherits `global.certManager.issuerRef.kind`. |
| concierge.tls.certManager.issuerRef.name | string | `""` | Name of the cert-manager issuer. Empty inherits `global.certManager.issuerRef.name`. |
| concierge.tls.secretNames | object | `{"api":"","impersonationProxy":""}` | Explicit secret names used by Concierge. |
| concierge.tls.secretNames.api | string | `""` | Secret name for the Concierge aggregated API serving certificate. |
| concierge.tls.secretNames.impersonationProxy | string | `""` | Secret name for the Concierge impersonation proxy serving certificate. |
| global | object | `{"certManager":{"enabled":false,"issuerRef":{"group":"cert-manager.io","kind":"Issuer","name":""}},"domain":"","gatewayAPI":{"enabled":false,"parentRefs":[]},"ingress":{"enabled":false,"provider":"traefik"}}` | Settings both components share. A component's own value wins, then `global`, then the built-in default. Set them once here instead of once per component. A boolean left at `null` and a string left at `""` in a component inherit from here, an explicit `false` or a value of its own does not. |
| global.certManager.enabled | bool | `false` | Use cert-manager for the TLS certificates of both components. |
| global.certManager.issuerRef | object | `{"group":"cert-manager.io","kind":"Issuer","name":""}` | cert-manager issuer for both Certificates. |
| global.certManager.issuerRef.group | string | `"cert-manager.io"` | API group of the issuer. |
| global.certManager.issuerRef.kind | string | `"Issuer"` | Kind of the issuer: `Issuer` or `ClusterIssuer`. |
| global.certManager.issuerRef.name | string | `""` | Name of the issuer. Empty uses the self-signed `Issuer` of each component when `createSelfSignedIssuer` is on. |
| global.domain | string | `""` | Base domain of both components. An empty `ingress.hostname` becomes `<ingress.hostPrefix>.<domain>`, so `domain: example.com` gives `supervisor.example.com` and `concierge.example.com`. That also feeds the TLS certificate names, the Supervisor's issuer URL and, by default, the JWTAuthenticator's issuer. |
| global.gatewayAPI.enabled | bool | `false` | Render a Gateway API route for both components. It is independent of `ingress`. |
| global.gatewayAPI.parentRefs | list | `[]` | Gateways both routes attach to. A component's own `gatewayAPI.parentRefs` wins. |
| global.ingress.enabled | bool | `false` | Expose both components through the provider below. |
| global.ingress.provider | string | `"traefik"` | Exposure provider for both components: `traefik` or `nginx`. Gateway API is set under `gatewayAPI`. |
| namespace | object | `{"create":true,"name":""}` | Global namespace settings for Pinniped components. |
| namespace.create | bool | `true` | Create the component namespaces (`<name>-concierge` and `<name>-supervisor`). |
| namespace.name | string | `""` | Base namespace prefix used to derive component namespaces. Empty defaults to `pinniped`. |
| supervisor | object | `{"config":{"allowedCiphersForTLSOneDotTwo":[],"apiGroupSuffix":"pinniped.dev","audit":{"logInternalPaths":"disabled","logUsernamesAndGroups":"disabled"},"endpoints":{},"httpsProxy":"","logLevel":"","noProxy":"$(KUBERNETES_SERVICE_HOST),169.254.169.254,127.0.0.1,localhost,.svc,.cluster.local"},"containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true,"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"customLabels":{},"enabled":true,"federationDomain":{"create":false,"identityProviders":[],"issuer":"","tlsSecretName":""},"gatewayAPI":{"annotations":{},"apiVersion":"","enabled":null,"hostname":"","hostnames":[],"parentRefs":[],"routeKind":"TLSRoute","routeName":"","service":{"name":"","port":443}},"identityProviders":{"dex":{"additionalScopes":["offline_access","groups","email"],"allowPasswordGrant":false,"certificateAuthorityData":"","clientID":"","clientSecret":"","clientSecretName":"","create":false,"createClientSecret":false,"displayName":"Dex","groupsClaim":"groups","issuer":"","name":"dex","usernameClaim":"email"},"github":{"allowedOrganizations":[],"certificateAuthorityData":"","clientID":"","clientSecret":"","clientSecretName":"","create":false,"createClientSecret":false,"displayName":"GitHub","groupsClaim":"slug","host":"","name":"github","organizationPolicy":"AllGitHubUsers","usernameClaim":"login:id"},"ldap":{"bindPassword":"","bindSecretName":"","bindUsername":"","certificateAuthorityData":"","create":false,"createBindSecret":false,"displayName":"LDAP","groupSearch":{"base":"","filter":"&(objectClass=groupOfNames)(member={})","groupNameAttribute":"cn"},"host":"","name":"openldap","userSearch":{"base":"","filter":"&(objectClass=inetOrgPerson)(uid={})","uidAttribute":"uidNumber","usernameAttribute":"uid"}}},"image":{"digest":"","pullPolicy":"IfNotPresent","repository":"ghcr.io/vmware/pinniped/pinniped-server","tag":""},"imagePullSecret":{"create":false,"dockerconfigjson":"","name":"image-pull-secret"},"ingress":{"annotations":{},"enabled":null,"hostPrefix":"supervisor","hostname":"","nginx":{"backendProtocol":"HTTPS","path":"/","pathType":"Prefix","sslPassthrough":"true","tlsSecretName":""},"provider":"","service":{"name":"","port":443},"traefik":{"entryPoints":["websecure"],"match":"","tlsPassthrough":true,"tlsSecretName":""}},"nameOverride":"","podSecurityContext":{"runAsGroup":65532,"runAsUser":65532},"replicaCount":1,"resources":{"limits":{"cpu":"1000m","memory":"128Mi"},"requests":{"cpu":"100m","memory":"128Mi"}},"service":{"api":{"port":443,"targetPort":10250},"public":{"clusterIP":{"enabled":false,"port":443},"loadBalancer":{"annotations":{},"enabled":false,"externalTrafficPolicy":"","loadBalancerClass":"","loadBalancerIP":"","loadBalancerSourceRanges":[],"port":443},"nodePort":{"enabled":false,"nodePort":null,"port":443}}},"tls":{"certManager":{"certificate":{"commonName":"","dnsNames":[],"duration":"","enabled":true,"privateKey":{"algorithm":"RSA","size":2048},"renewBefore":"","secretName":""},"createSelfSignedIssuer":false,"enabled":null,"issuerRef":{"group":"","kind":"","name":""}},"secretName":""}}` | Pinniped Supervisor component configuration. |
| supervisor.config | object | `{"allowedCiphersForTLSOneDotTwo":[],"apiGroupSuffix":"pinniped.dev","audit":{"logInternalPaths":"disabled","logUsernamesAndGroups":"disabled"},"endpoints":{},"httpsProxy":"","logLevel":"","noProxy":"$(KUBERNETES_SERVICE_HOST),169.254.169.254,127.0.0.1,localhost,.svc,.cluster.local"}` | Supervisor static configuration rendered into the Pinniped config file. |
| supervisor.config.allowedCiphersForTLSOneDotTwo | list | `[]` | Allowed TLS 1.2 cipher suites for Supervisor. Empty uses Pinniped defaults. |
| supervisor.config.apiGroupSuffix | string | `"pinniped.dev"` | API group suffix for Supervisor APIs. |
| supervisor.config.audit | object | `{"logInternalPaths":"disabled","logUsernamesAndGroups":"disabled"}` | Supervisor audit logging configuration. |
| supervisor.config.audit.logInternalPaths | string | `"disabled"` | Include internal endpoints such as `/healthz` in Supervisor audit logs. |
| supervisor.config.audit.logUsernamesAndGroups | string | `"disabled"` | Include usernames and groups in Supervisor audit logs. |
| supervisor.config.endpoints | object | `{}` | Raw Supervisor endpoint configuration merged into `pinniped.yaml`. |
| supervisor.config.httpsProxy | string | `""` | HTTPS proxy used by Supervisor for outbound requests. |
| supervisor.config.logLevel | string | `""` | Supervisor log level. Leave empty for Pinniped defaults. |
| supervisor.config.noProxy | string | `"$(KUBERNETES_SERVICE_HOST),169.254.169.254,127.0.0.1,localhost,.svc,.cluster.local"` | NO_PROXY list used by Supervisor for outbound requests. |
| supervisor.containerSecurityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true,"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}}` | Container-level security context for the Supervisor container. |
| supervisor.containerSecurityContext.allowPrivilegeEscalation | bool | `false` | Disable privilege escalation in the Supervisor container. |
| supervisor.containerSecurityContext.capabilities | object | `{"drop":["ALL"]}` | Linux capabilities configuration for the Supervisor container. |
| supervisor.containerSecurityContext.capabilities.drop | list | `["ALL"]` | Capabilities dropped from the Supervisor container. |
| supervisor.containerSecurityContext.readOnlyRootFilesystem | bool | `true` | Mount the root filesystem as read-only. |
| supervisor.containerSecurityContext.runAsNonRoot | bool | `true` | Require the Supervisor container to run as a non-root user. |
| supervisor.containerSecurityContext.seccompProfile | object | `{"type":"RuntimeDefault"}` | Seccomp profile applied to the Supervisor container. |
| supervisor.containerSecurityContext.seccompProfile.type | string | `"RuntimeDefault"` | Seccomp profile type. |
| supervisor.customLabels | object | `{}` | Additional labels applied only to Supervisor resources. |
| supervisor.enabled | bool | `true` | Enable Supervisor resources. |
| supervisor.federationDomain | object | `{"create":false,"identityProviders":[],"issuer":"","tlsSecretName":""}` | FederationDomain configures the Supervisor as an OIDC issuer for downstream clusters. |
| supervisor.federationDomain.create | bool | `false` | Create a FederationDomain resource. |
| supervisor.federationDomain.identityProviders | list | `[]` | Each entry must have `displayName` and `objectRef.{apiGroup,kind,name}` fields. ref: https://pinniped.dev/docs/howto/supervisor/configure-supervisor-federationdomain-idps/ |
| supervisor.federationDomain.issuer | string | `""` | OIDC issuer URL. Must be a publicly reachable HTTPS URL and must exactly match `concierge.jwtAuthenticator.issuer`. |
| supervisor.federationDomain.tlsSecretName | string | `""` | Defaults to the cert-manager-managed secret when `supervisor.tls.certManager.enabled=true`. |
| supervisor.gatewayAPI | object | `{"annotations":{},"apiVersion":"","enabled":null,"hostname":"","hostnames":[],"parentRefs":[],"routeKind":"TLSRoute","routeName":"","service":{"name":"","port":443}}` | Gateway API route for Supervisor. It is separate from `ingress`: enable one, the other, or both. The route is a `TLSRoute` (SNI passthrough) or a `TCPRoute`, so the Gateway needs a TLS passthrough or TCP listener. |
| supervisor.gatewayAPI.annotations | object | `{}` | Additional annotations on the route. |
| supervisor.gatewayAPI.apiVersion | string | `""` | API version of the route. Empty picks one for the kind: `gateway.networking.k8s.io/v1` for a `TLSRoute`, `gateway.networking.k8s.io/v1alpha2` for a `TCPRoute`. Set it to match the Gateway API CRDs you installed. |
| supervisor.gatewayAPI.enabled | string | `nil` | Render the Gateway API route for Supervisor. `null` inherits `global.gatewayAPI.enabled`. |
| supervisor.gatewayAPI.hostname | string | `""` | Hostname of a `TLSRoute`. Empty uses the `ingress` hostname, which is `<ingress.hostPrefix>.<global.domain>` when unset. |
| supervisor.gatewayAPI.hostnames | list | `[]` | Several hostnames for a `TLSRoute`. Wins over `hostname`. |
| supervisor.gatewayAPI.parentRefs | list | `[]` | Gateways the route attaches to. Empty inherits `global.gatewayAPI.parentRefs`. One is required. |
| supervisor.gatewayAPI.routeKind | string | `"TLSRoute"` | Route kind: `TLSRoute` (matches the SNI hostnames) or `TCPRoute` (plain TCP, no hostnames). |
| supervisor.gatewayAPI.routeName | string | `""` | Override the generated route name. |
| supervisor.gatewayAPI.service | object | `{"name":"","port":443}` | Backend of the route. It does not follow `ingress.service`. |
| supervisor.gatewayAPI.service.name | string | `""` | Explicit backend service name. Empty uses the same service the ingress would. |
| supervisor.gatewayAPI.service.port | int | `443` | Backend service port. |
| supervisor.identityProviders | object | `{"dex":{"additionalScopes":["offline_access","groups","email"],"allowPasswordGrant":false,"certificateAuthorityData":"","clientID":"","clientSecret":"","clientSecretName":"","create":false,"createClientSecret":false,"displayName":"Dex","groupsClaim":"groups","issuer":"","name":"dex","usernameClaim":"email"},"github":{"allowedOrganizations":[],"certificateAuthorityData":"","clientID":"","clientSecret":"","clientSecretName":"","create":false,"createClientSecret":false,"displayName":"GitHub","groupsClaim":"slug","host":"","name":"github","organizationPolicy":"AllGitHubUsers","usernameClaim":"login:id"},"ldap":{"bindPassword":"","bindSecretName":"","bindUsername":"","certificateAuthorityData":"","create":false,"createBindSecret":false,"displayName":"LDAP","groupSearch":{"base":"","filter":"&(objectClass=groupOfNames)(member={})","groupNameAttribute":"cn"},"host":"","name":"openldap","userSearch":{"base":"","filter":"&(objectClass=inetOrgPerson)(uid={})","uidAttribute":"uidNumber","usernameAttribute":"uid"}}}` | Identity provider resources created in the Supervisor namespace. |
| supervisor.identityProviders.dex | object | `{"additionalScopes":["offline_access","groups","email"],"allowPasswordGrant":false,"certificateAuthorityData":"","clientID":"","clientSecret":"","clientSecretName":"","create":false,"createClientSecret":false,"displayName":"Dex","groupsClaim":"groups","issuer":"","name":"dex","usernameClaim":"email"}` | Dex OIDC identity provider configuration. |
| supervisor.identityProviders.dex.additionalScopes | list | `["offline_access","groups","email"]` | Additional OIDC scopes to request from Dex beyond `openid`. |
| supervisor.identityProviders.dex.allowPasswordGrant | bool | `false` | Allow the OIDC password grant flow. Requires Dex >= v2.31.0. |
| supervisor.identityProviders.dex.certificateAuthorityData | string | `""` | Base64-encoded PEM CA bundle for validating the Dex TLS certificate. Omit when Dex uses a publicly trusted CA. |
| supervisor.identityProviders.dex.clientID | string | `""` | Dex OAuth client ID. Required when `createClientSecret=true`. |
| supervisor.identityProviders.dex.clientSecret | string | `""` | Dex OAuth client secret. Required when `createClientSecret=true`. |
| supervisor.identityProviders.dex.clientSecretName | string | `""` | Name of the Secret containing the Dex client credentials. |
| supervisor.identityProviders.dex.create | bool | `false` | Create an OIDCIdentityProvider for Dex. |
| supervisor.identityProviders.dex.createClientSecret | bool | `false` | Create the Dex client credentials Secret from the values below. |
| supervisor.identityProviders.dex.displayName | string | `"Dex"` | Display name shown to users at the login-chooser screen. |
| supervisor.identityProviders.dex.groupsClaim | string | `"groups"` | OIDC claim mapped to Kubernetes group membership. |
| supervisor.identityProviders.dex.issuer | string | `""` | Dex OIDC issuer URL (e.g. `https://dex.example.com`). |
| supervisor.identityProviders.dex.name | string | `"dex"` | Name of the OIDCIdentityProvider resource. |
| supervisor.identityProviders.dex.usernameClaim | string | `"email"` | OIDC claim mapped to the Kubernetes username. |
| supervisor.identityProviders.github | object | `{"allowedOrganizations":[],"certificateAuthorityData":"","clientID":"","clientSecret":"","clientSecretName":"","create":false,"createClientSecret":false,"displayName":"GitHub","groupsClaim":"slug","host":"","name":"github","organizationPolicy":"AllGitHubUsers","usernameClaim":"login:id"}` | GitHub identity provider configuration. |
| supervisor.identityProviders.github.allowedOrganizations | list | `[]` | List of GitHub organizations to allow when `organizationPolicy=OnlyUsersFromAllowedOrganizations`. |
| supervisor.identityProviders.github.certificateAuthorityData | string | `""` | Base64-encoded PEM CA bundle for GitHub Enterprise TLS. Omit for `github.com`. |
| supervisor.identityProviders.github.clientID | string | `""` | GitHub OAuth App or GitHub App client ID. Required when `createClientSecret=true`. |
| supervisor.identityProviders.github.clientSecret | string | `""` | GitHub OAuth App or GitHub App client secret. Required when `createClientSecret=true`. |
| supervisor.identityProviders.github.clientSecretName | string | `""` | Name of the Secret containing the GitHub OAuth App client credentials. |
| supervisor.identityProviders.github.create | bool | `false` | Create a GitHubIdentityProvider resource. |
| supervisor.identityProviders.github.createClientSecret | bool | `false` | Create the GitHub client credentials Secret from the values below. |
| supervisor.identityProviders.github.displayName | string | `"GitHub"` | Display name shown to users at the login-chooser screen. |
| supervisor.identityProviders.github.groupsClaim | string | `"slug"` | How to map GitHub teams to Kubernetes groups: `name` or `slug`. |
| supervisor.identityProviders.github.host | string | `""` | GitHub API host. Leave empty for `github.com`; set for GitHub Enterprise Server. |
| supervisor.identityProviders.github.name | string | `"github"` | Name of the GitHubIdentityProvider resource. |
| supervisor.identityProviders.github.organizationPolicy | string | `"AllGitHubUsers"` | GitHub organization membership policy: `AllGitHubUsers` or `OnlyUsersFromAllowedOrganizations`. |
| supervisor.identityProviders.github.usernameClaim | string | `"login:id"` | How to map the GitHub identity to a Kubernetes username: `id`, `login`, or `login:id`. |
| supervisor.identityProviders.ldap | object | `{"bindPassword":"","bindSecretName":"","bindUsername":"","certificateAuthorityData":"","create":false,"createBindSecret":false,"displayName":"LDAP","groupSearch":{"base":"","filter":"&(objectClass=groupOfNames)(member={})","groupNameAttribute":"cn"},"host":"","name":"openldap","userSearch":{"base":"","filter":"&(objectClass=inetOrgPerson)(uid={})","uidAttribute":"uidNumber","usernameAttribute":"uid"}}` | LDAP identity provider configuration. |
| supervisor.identityProviders.ldap.bindPassword | string | `""` | LDAP bind account password. Required when `createBindSecret=true`. |
| supervisor.identityProviders.ldap.bindSecretName | string | `""` | Name of the Secret containing the LDAP bind account credentials. |
| supervisor.identityProviders.ldap.bindUsername | string | `""` | LDAP bind account distinguished name. Required when `createBindSecret=true`. |
| supervisor.identityProviders.ldap.certificateAuthorityData | string | `""` | Base64-encoded PEM CA bundle for the LDAP server TLS certificate. |
| supervisor.identityProviders.ldap.create | bool | `false` | Create an LDAPIdentityProvider resource. |
| supervisor.identityProviders.ldap.createBindSecret | bool | `false` | Create the LDAP bind account Secret from the values below. |
| supervisor.identityProviders.ldap.displayName | string | `"LDAP"` | Display name shown to users at the login-chooser screen. |
| supervisor.identityProviders.ldap.groupSearch | object | `{"base":"","filter":"&(objectClass=groupOfNames)(member={})","groupNameAttribute":"cn"}` | LDAP group search settings. |
| supervisor.identityProviders.ldap.groupSearch.base | string | `""` | Base DN for group searches. |
| supervisor.identityProviders.ldap.groupSearch.filter | string | `"&(objectClass=groupOfNames)(member={})"` | LDAP filter expression for group membership lookups. |
| supervisor.identityProviders.ldap.groupSearch.groupNameAttribute | string | `"cn"` | LDAP attribute used as the Kubernetes group name. |
| supervisor.identityProviders.ldap.host | string | `""` | LDAP server host and optional port (e.g. `ldap.example.com:636`). |
| supervisor.identityProviders.ldap.name | string | `"openldap"` | Name of the LDAPIdentityProvider resource. |
| supervisor.identityProviders.ldap.userSearch | object | `{"base":"","filter":"&(objectClass=inetOrgPerson)(uid={})","uidAttribute":"uidNumber","usernameAttribute":"uid"}` | LDAP user search settings. |
| supervisor.identityProviders.ldap.userSearch.base | string | `""` | Base DN for user searches. |
| supervisor.identityProviders.ldap.userSearch.filter | string | `"&(objectClass=inetOrgPerson)(uid={})"` | LDAP filter expression for user lookups. Use `{}` as a placeholder for the supplied username. |
| supervisor.identityProviders.ldap.userSearch.uidAttribute | string | `"uidNumber"` | LDAP attribute used as the stable unique user identifier. |
| supervisor.identityProviders.ldap.userSearch.usernameAttribute | string | `"uid"` | LDAP attribute used as the Kubernetes username. |
| supervisor.image | object | `{"digest":"","pullPolicy":"IfNotPresent","repository":"ghcr.io/vmware/pinniped/pinniped-server","tag":""}` | Supervisor container image settings. |
| supervisor.image.digest | string | `""` | Supervisor image digest. Takes precedence over `tag` when set. |
| supervisor.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the Supervisor container. |
| supervisor.image.repository | string | `"ghcr.io/vmware/pinniped/pinniped-server"` | Supervisor image repository. |
| supervisor.image.tag | string | `""` | Supervisor image tag. Defaults to the chart appVersion when empty. |
| supervisor.imagePullSecret | object | `{"create":false,"dockerconfigjson":"","name":"image-pull-secret"}` | Optional image pull secret configuration for private registries. |
| supervisor.imagePullSecret.create | bool | `false` | Create a dockerconfigjson secret for pulling the Pinniped image. |
| supervisor.imagePullSecret.dockerconfigjson | string | `""` | Base64-encoded `.dockerconfigjson` payload used when `create=true`. |
| supervisor.imagePullSecret.name | string | `"image-pull-secret"` | Name of the image pull secret. |
| supervisor.ingress | object | `{"annotations":{},"enabled":null,"hostPrefix":"supervisor","hostname":"","nginx":{"backendProtocol":"HTTPS","path":"/","pathType":"Prefix","sslPassthrough":"true","tlsSecretName":""},"provider":"","service":{"name":"","port":443},"traefik":{"entryPoints":["websecure"],"match":"","tlsPassthrough":true,"tlsSecretName":""}}` | Supervisor ingress settings for Traefik or NGINX passthrough. |
| supervisor.ingress.annotations | object | `{}` | Additional annotations applied to the Supervisor ingress resources. |
| supervisor.ingress.enabled | string | `nil` | Enable ingress exposure (Traefik or NGINX) for Supervisor. `null` inherits `global.ingress.enabled`. |
| supervisor.ingress.hostPrefix | string | `"supervisor"` | First label of the hostname built from `global.domain`. |
| supervisor.ingress.hostname | string | `""` | Primary hostname used by Supervisor passthrough exposure. Empty becomes `<hostPrefix>.<global.domain>` when `global.domain` is set. |
| supervisor.ingress.nginx | object | `{"backendProtocol":"HTTPS","path":"/","pathType":"Prefix","sslPassthrough":"true","tlsSecretName":""}` | NGINX SSL passthrough ingress settings. |
| supervisor.ingress.nginx.backendProtocol | string | `"HTTPS"` | Value for the `nginx.ingress.kubernetes.io/backend-protocol` annotation. |
| supervisor.ingress.nginx.path | string | `"/"` | HTTP path used by the compatibility ingress resource. |
| supervisor.ingress.nginx.pathType | string | `"Prefix"` | Path type used by the compatibility ingress resource. |
| supervisor.ingress.nginx.sslPassthrough | string | `"true"` | Value for the `nginx.ingress.kubernetes.io/ssl-passthrough` annotation. |
| supervisor.ingress.nginx.tlsSecretName | string | `""` | TLS secret name for SSL. Typically the cert-manager-managed secret name. |
| supervisor.ingress.provider | string | `""` | Exposure provider (`traefik` or `nginx`). Empty inherits `global.ingress.provider`. |
| supervisor.ingress.service | object | `{"name":"","port":443}` | Backend service override used by the ingress. |
| supervisor.ingress.service.name | string | `""` | Explicit service name used as the ingress backend. |
| supervisor.ingress.service.port | int | `443` | Service port used as the ingress backend. |
| supervisor.ingress.traefik | object | `{"entryPoints":["websecure"],"match":"","tlsPassthrough":true,"tlsSecretName":""}` | Traefik `IngressRouteTCP` settings. |
| supervisor.ingress.traefik.entryPoints | list | `["websecure"]` | EntryPoints attached to the Traefik TCP route. |
| supervisor.ingress.traefik.match | string | `""` | Optional custom Traefik TCP match expression. Defaults to `HostSNI(hostname)`. |
| supervisor.ingress.traefik.tlsPassthrough | bool | `true` | Enable TLS passthrough for Traefik TCP routing. |
| supervisor.ingress.traefik.tlsSecretName | string | `""` | TLS secret name for SSL. Typically the cert-manager-managed secret name. |
| supervisor.nameOverride | string | `""` | Override the default Supervisor resource name prefix. |
| supervisor.podSecurityContext | object | `{"runAsGroup":65532,"runAsUser":65532}` | Pod-level security context for Supervisor pods. |
| supervisor.podSecurityContext.runAsGroup | int | `65532` | GID used to run the Supervisor pod. |
| supervisor.podSecurityContext.runAsUser | int | `65532` | UID used to run the Supervisor pod. |
| supervisor.replicaCount | int | `1` | Number of Supervisor replicas. |
| supervisor.resources | object | `{"limits":{"cpu":"1000m","memory":"128Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits for the Supervisor container. |
| supervisor.resources.limits | object | `{"cpu":"1000m","memory":"128Mi"}` | Resource limits for the Supervisor container. |
| supervisor.resources.limits.cpu | string | `"1000m"` | CPU limit for the Supervisor container. |
| supervisor.resources.limits.memory | string | `"128Mi"` | Memory limit for the Supervisor container. |
| supervisor.resources.requests | object | `{"cpu":"100m","memory":"128Mi"}` | Resource requests for the Supervisor container. |
| supervisor.resources.requests.cpu | string | `"100m"` | Requested CPU for the Supervisor container. |
| supervisor.resources.requests.memory | string | `"128Mi"` | Requested memory for the Supervisor container. |
| supervisor.service | object | `{"api":{"port":443,"targetPort":10250},"public":{"clusterIP":{"enabled":false,"port":443},"loadBalancer":{"annotations":{},"enabled":false,"externalTrafficPolicy":"","loadBalancerClass":"","loadBalancerIP":"","loadBalancerSourceRanges":[],"port":443},"nodePort":{"enabled":false,"nodePort":null,"port":443}}}` | Service settings for Supervisor API and public access. |
| supervisor.service.api | object | `{"port":443,"targetPort":10250}` | Service exposing the aggregated Supervisor API. |
| supervisor.service.api.port | int | `443` | External service port for the Supervisor API service. |
| supervisor.service.api.targetPort | int | `10250` | Container target port for the Supervisor API service. |
| supervisor.service.public | object | `{"clusterIP":{"enabled":false,"port":443},"loadBalancer":{"annotations":{},"enabled":false,"externalTrafficPolicy":"","loadBalancerClass":"","loadBalancerIP":"","loadBalancerSourceRanges":[],"port":443},"nodePort":{"enabled":false,"nodePort":null,"port":443}}` | Public exposure service settings for the Supervisor HTTPS endpoint. |
| supervisor.service.public.clusterIP | object | `{"enabled":false,"port":443}` | ClusterIP-based public exposure settings. |
| supervisor.service.public.clusterIP.enabled | bool | `false` | Create a dedicated ClusterIP service for Supervisor HTTPS traffic. |
| supervisor.service.public.clusterIP.port | int | `443` | External port exposed by the ClusterIP service. |
| supervisor.service.public.loadBalancer | object | `{"annotations":{},"enabled":false,"externalTrafficPolicy":"","loadBalancerClass":"","loadBalancerIP":"","loadBalancerSourceRanges":[],"port":443}` | LoadBalancer-based public exposure settings. |
| supervisor.service.public.loadBalancer.annotations | object | `{}` | Additional annotations for the Supervisor LoadBalancer service. |
| supervisor.service.public.loadBalancer.enabled | bool | `false` | Create a LoadBalancer service for Supervisor HTTPS traffic. |
| supervisor.service.public.loadBalancer.externalTrafficPolicy | string | `""` | Optional external traffic policy for the Supervisor LoadBalancer service. |
| supervisor.service.public.loadBalancer.loadBalancerClass | string | `""` | Optional `loadBalancerClass` for the Supervisor LoadBalancer service. |
| supervisor.service.public.loadBalancer.loadBalancerIP | string | `""` | Static load balancer IP for the Supervisor LoadBalancer service. |
| supervisor.service.public.loadBalancer.loadBalancerSourceRanges | list | `[]` | Optional source ranges allowed to reach the Supervisor LoadBalancer service. |
| supervisor.service.public.loadBalancer.port | int | `443` | External port exposed by the LoadBalancer service. |
| supervisor.service.public.nodePort | object | `{"enabled":false,"nodePort":null,"port":443}` | NodePort-based public exposure settings. |
| supervisor.service.public.nodePort.enabled | bool | `false` | Create a NodePort service for Supervisor HTTPS traffic. |
| supervisor.service.public.nodePort.nodePort | string | `nil` | Fixed nodePort value. Leave null to let Kubernetes allocate one. |
| supervisor.service.public.nodePort.port | int | `443` | External port exposed by the NodePort service. |
| supervisor.tls | object | `{"certManager":{"certificate":{"commonName":"","dnsNames":[],"duration":"","enabled":true,"privateKey":{"algorithm":"RSA","size":2048},"renewBefore":"","secretName":""},"createSelfSignedIssuer":false,"enabled":null,"issuerRef":{"group":"","kind":"","name":""}},"secretName":""}` | TLS secret and optional cert-manager configuration for Supervisor. |
| supervisor.tls.certManager | object | `{"certificate":{"commonName":"","dnsNames":[],"duration":"","enabled":true,"privateKey":{"algorithm":"RSA","size":2048},"renewBefore":"","secretName":""},"createSelfSignedIssuer":false,"enabled":null,"issuerRef":{"group":"","kind":"","name":""}}` | Optional cert-manager integration for Supervisor certificates. |
| supervisor.tls.certManager.certificate | object | `{"commonName":"","dnsNames":[],"duration":"","enabled":true,"privateKey":{"algorithm":"RSA","size":2048},"renewBefore":"","secretName":""}` | cert-manager certificate options for Supervisor. |
| supervisor.tls.certManager.certificate.commonName | string | `""` | Optional common name used in the Supervisor certificate. |
| supervisor.tls.certManager.certificate.dnsNames | list | `[]` | DNS names included in the Supervisor certificate. |
| supervisor.tls.certManager.certificate.duration | string | `""` | Optional certificate duration passed to cert-manager. |
| supervisor.tls.certManager.certificate.enabled | bool | `true` | Create a cert-manager `Certificate` for Supervisor. |
| supervisor.tls.certManager.certificate.privateKey | object | `{"algorithm":"RSA","size":2048}` | Private key settings used by cert-manager. |
| supervisor.tls.certManager.certificate.privateKey.algorithm | string | `"RSA"` | Private key algorithm for the Supervisor certificate. |
| supervisor.tls.certManager.certificate.privateKey.size | int | `2048` | Private key size for the Supervisor certificate. |
| supervisor.tls.certManager.certificate.renewBefore | string | `""` | Optional renew-before duration passed to cert-manager. |
| supervisor.tls.certManager.certificate.secretName | string | `""` | Override the secret name written by the cert-manager `Certificate`. |
| supervisor.tls.certManager.createSelfSignedIssuer | bool | `false` | Create a simple self-signed `Issuer` in the Supervisor namespace. |
| supervisor.tls.certManager.enabled | string | `nil` | Enable cert-manager resources for Supervisor. `null` inherits `global.certManager.enabled`. |
| supervisor.tls.certManager.issuerRef | object | `{"group":"","kind":"","name":""}` | cert-manager issuer reference used by the Supervisor certificate. |
| supervisor.tls.certManager.issuerRef.group | string | `""` | API group of the cert-manager issuer or clusterissuer resource. Empty inherits `global.certManager.issuerRef.group`. |
| supervisor.tls.certManager.issuerRef.kind | string | `""` | Kind of the cert-manager issuer or clusterissuer resource. Empty inherits `global.certManager.issuerRef.kind`. |
| supervisor.tls.certManager.issuerRef.name | string | `""` | Name of the cert-manager issuer. Empty inherits `global.certManager.issuerRef.name`. |
| supervisor.tls.secretName | string | `""` | Secret name used by the Supervisor default TLS certificate. |

