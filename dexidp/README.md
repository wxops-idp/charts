# dexidp

![Version: 0.1.1](https://img.shields.io/badge/Version-0.1.1-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: v2.45.1](https://img.shields.io/badge/AppVersion-v2.45.1-informational?style=flat-square)

A thin wrapper around the upstream Dex chart that wires its configuration and secrets through External Secrets Operator.

>[!NOTE]
>This chart does not re-implement Dex. It depends on the upstream [Dex chart](https://github.com/dexidp/helm-charts/tree/master/charts/dex) and adds one thing: an `ExternalSecret` that generates Dex's `config.yaml` from a secret backend such as OpenBao. Every upstream value is set under the `dex:` key.

## How it works

```text
OpenBao (KV v2)                     External Secrets Operator                 Dex
dex/connectors/<name>  ──find──┐
dex/clients/<name>     ──find──┼──▶  template + static base  ──▶  Secret dex-config  ──mount──▶  pod
                               │      (validates every entry)        (config.yaml)                 ▲
Git (values): dynamicConfig.base ──────────┘                                                       │
                                                        Stakater Reloader restarts the pod ────────┘
```

- **Content lives in the store.** A connector, a static client or a local user is one JSON secret. Adding, changing or removing one is a write to OpenBao, with no chart change and no GitOps commit.
- **Settings live in Git.** `dynamicConfig.base` holds `issuer`, `storage`, `web` and other values that rarely change. Connectors and clients listed there are kept and merged with the ones from the store.
- **Dex restarts to apply changes.** Dex does not reload its config. ESO polls the store every `dynamicConfig.refreshInterval`, updates the Secret, and [Stakater Reloader](https://github.com/stakater/Reloader) restarts the pod. The default `reloader.stakater.com/auto` annotation is already set. Without Reloader the Secret still updates, but the pod keeps the old config until you restart it.

## OpenBao layout

Paths in `dynamicConfig.sources` are relative to the KV mount that the SecretStore points at. Each secret holds one JSON object.

Connector, `dex/connectors/github`:

```json
{
  "type": "github",
  "id": "github",
  "name": "GitHub",
  "config": {
    "clientID": "<id>",
    "clientSecret": "<secret>",
    "redirectURI": "https://dex.example.com/callback"
  }
}
```

Static client, `dex/clients/pinniped`:

```json
{
  "id": "pinniped",
  "name": "Pinniped Supervisor",
  "secret": "<client-secret>",
  "redirectURIs": ["https://supervisor.example.com/callback"]
}
```

```bash
bao kv put -mount=wxops dex/connectors/github @github.json
bao kv put -mount=wxops dex/clients/pinniped @pinniped.json
```

A connector needs `type`, `id`, `name` and `config`. A client needs `id`, `name`, `redirectURIs` and one of `secret`, `secretEnv` or `public`. `config` may be a nested object or a JSON string, and `redirectURIs` may be a list or a JSON list inside a string, because some tools store lists that way. Both end up as the same list in the Dex config.

### Local users (bootstrap admin)

Local accounts are Dex `staticPasswords`, not `staticClients`. Each one is a secret under `dex/users/`, and any user found turns on `enablePasswordDB` unless `dynamicConfig.base` already sets it, in which case your value wins. Set `dynamicConfig.sources.users.enabled=false` to use external connectors only.

Dex stores a bcrypt hash, not the password. The hash is computed once, outside ESO, because bcrypt adds a random salt: hashing inside the template would change the config on every sync and restart Dex each time. The template rejects a `hash` that does not start with `$2`, so a plain password cannot be stored by mistake.

```bash
read -rs -p 'Password: ' PW; echo
HASH=$(htpasswd -bnBC 10 "" "$PW" | tr -d ':\n' | sed 's/^\$2y/$2a/')

jq -n --arg hash "$HASH" --arg id "$(uuidgen)" '{
  email: "admin@wxops.cloud", username: "admin", name: "Administrator",
  userID: $id, hash: $hash, groups: ["wxops-admins"]
}' | bao kv put -mount=wxops dex/users/admin -
```

A user needs `email`, `username`, `userID` and `hash`. The optional fields `name`, `emailVerified`, `preferredUsername` and `groups` are passed through as they are, see the [Dex example](https://github.com/dexidp/dex/blob/master/config.yaml.dist). `groups` must be a list of strings, or a JSON list inside a string (`"[\"admins\"]"`) for tools that store lists that way, and becomes the `groups` claim when the client asks for the `groups` scope. Users sign in with their **email**, and `username` is the display login. Downstream apps read the `email` claim, so use a real address unless you are sure every app accepts a bare `admin`.

Do not commit a default password to this repository or to your values. Choose it when you write the hash to OpenBao, and rotate it once the real identity providers are in place.

## Connecting ESO to OpenBao

Use Kubernetes auth so ESO authenticates with its own short-lived ServiceAccount token. Dex is then only a consumer of the synced Secret and takes no part in authentication, which avoids a bootstrap cycle if Dex also signs people in to OpenBao.

Give the role read-only access to the Dex paths and bind it to one ServiceAccount and namespace:

```hcl
path "wxops/data/dex/*"     { capabilities = ["read"] }
path "wxops/metadata/dex/*" { capabilities = ["read", "list"] }
```

```yaml
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata:
  name: dex-openbao
  namespace: idp
spec:
  provider:
    vault:
      server: http://openbao.openbao.svc:8200
      path: wxops
      version: v2
      auth:
        kubernetes:
          mountPath: kubernetes
          role: dex-eso
          serviceAccountRef:
            name: dex-eso
```

Set `externalSecretDefaults.secretStoreRef.name: dex-openbao`. The chart does not create the store or the OpenBao role, they belong to your secret-management layer.

## When something is wrong

The template validates every entry and fails the sync on anything malformed: invalid JSON, a missing required field, a duplicate `id`, `email` or `userID`, a client with no `secret`, `secretEnv` or `public`, a user whose `hash` is not bcrypt, a client whose `redirectURIs` or a user whose `groups` is not a list of strings, or no connector and no user at all. When a sync fails, ESO keeps the previous Secret, so Dex keeps running on the last good config. The reason is in the ExternalSecret status:

```bash
kubectl -n idp describe externalsecret dex-config
```

An invalid entry therefore blocks all later changes until it is fixed, and it fails loudly instead of silently dropping the entry.

### Empty paths are not an error

Connectors, clients and users are all optional. The ExternalSecret sets `deletionPolicy: Merge` (`dynamicConfig.deletionPolicy`), so a scanned path with no secret is skipped, and ESO records a normal `missing provider secret` event instead of failing. A fresh install with only `dynamicConfig.base` renders as long as the base sets `enablePasswordDB: true` or lists a connector, because Dex needs one of them to start.

With ESO's own default, `Retain`, an empty path fails the whole sync with `Secret does not exist` and `dex-config` is never created. Do not set `Delete`: when every source is empty it removes the Secret and takes Dex's config with it.

## Static mode

To use plain Helm values instead, set `dynamicConfig.enabled=false`, `dex.configSecret.create=true` and put the config under `dex.config`. Use the `externalSecrets` map for any extra Secret, such as a database password exposed through `dex.envFrom`.

## Not yet verified on a cluster

The chart is linted and rendered with `helm template`, and the ESO template logic was run through Helm's Go template engine with valid and invalid entries. These points still need a run against a real External Secrets Operator and OpenBao:

- `dataFrom.find` with `rewrite` returns the expected `connector_`, `client_` and `user_` keys, and an empty path is skipped with `deletionPolicy: Merge` instead of failing the sync. This follows External Secrets Operator v1.2.1's source and is not yet confirmed on a cluster.
- ESO's template engine provides `fail`, `fromJson`, `toYaml`, `concat` and `kindIs`, and renders large integers as plain numbers.
- On a failed sync the old Secret stays in place, and with one replica the old pod keeps serving while a new pod fails to start.
- Reloader restarts the pod when the Secret changes.
- A local user written with the commands above can sign in to Dex, and the `groups` claim reaches the client.

## Using Dex with Pinniped

Store the Pinniped Supervisor as a client under `dex/clients/pinniped`, with `redirectURIs` ending in `/callback`. On the Pinniped side, enable `supervisor.identityProviders.dex` in the [pinniped chart](../pinniped) with the same `clientID` and secret.

## Installing the Chart

```bash
helm repo add wxops https://charts.wxops.cloud
helm install dex wxops/dexidp -n idp --create-namespace \
  --set externalSecretDefaults.secretStoreRef.name=dex-openbao
```

For local rendering and testing:

```bash
helm dependency build
helm template dex . -f values-test.yaml
helm lint . -f values-test.yaml
```

## Uninstalling the Chart

```bash
helm uninstall dex -n idp
```

**Homepage:** <https://dexidp.io/>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| Xeus Nguyen | <xeusnguyen@gmail.com> | <https://wiki.xeusnguyen.xyz> |

## Source Code

* <https://github.com/dexidp/dex>
* <https://github.com/dexidp/helm-charts/tree/master/charts/dex>

## Requirements

| Repository | Name | Version |
|------------|------|---------|
| https://charts.dexidp.io | dex | 0.25.2 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| dex | object | `{"config":{},"configSecret":{"create":false,"name":"dex-config"},"envFrom":[],"fullnameOverride":"","nameOverride":"","namespaceOverride":"","podAnnotations":{"reloader.stakater.com/auto":"true"}}` | Values for the upstream Dex chart (https://github.com/dexidp/helm-charts/tree/master/charts/dex). Only the settings this wrapper cares about are listed. Everything else in the upstream `values.yaml` works here too. |
| dex.config | object | `{}` | Only used when `dynamicConfig.enabled=false` and `dex.configSecret.create=true`. See https://dexidp.io/docs/. |
| dex.configSecret.create | bool | `false` | Let the Dex chart create the config Secret from `dex.config`. Keep false while `dynamicConfig.enabled=true`. |
| dex.configSecret.name | string | `"dex-config"` | Secret holding the `config.yaml` key. Must equal `dynamicConfig.secretName`. |
| dex.envFrom | list | `[]` | Secrets and ConfigMaps exposed as environment variables, for example the `env` ExternalSecret above. |
| dex.fullnameOverride | string | `""` | Override the full resource name. |
| dex.nameOverride | string | `""` | Override the chart name used in resource names. |
| dex.namespaceOverride | string | `""` | Namespace to render into. Defaults to the release namespace. |
| dex.podAnnotations | object | `{"reloader.stakater.com/auto":"true"}` | Extra pod annotations. Dex does not reload its config, so a synced Secret only takes effect after a restart. The default annotation makes Stakater Reloader restart the pod when a referenced Secret changes. It is harmless without Reloader. |
| dynamicConfig | object | `{"base":{"enablePasswordDB":true,"issuer":"https://dex.example.com","oauth2":{"skipApprovalScreen":true},"signer":{"config":{"algorithm":"RS256","keysRotationPeriod":"6h"},"type":"local"},"storage":{"config":{"inCluster":true},"type":"kubernetes"},"web":{"http":"0.0.0.0:5556"}},"deletionPolicy":"Merge","enabled":true,"refreshInterval":"1m","secretName":"dex-config","secretStoreRef":{},"sources":{"clients":{"nameRegexp":".*","path":"dex/clients"},"connectors":{"nameRegexp":".*","path":"dex/connectors"},"users":{"enabled":true,"nameRegexp":".*","path":"dex/users"}}}` | Builds the Dex `config.yaml` from a secret backend (for example OpenBao) instead of from Helm values. One ExternalSecret scans the connector and client paths, and its template merges the entries with `base` into the final config. Adding, changing or removing a connector or client is a write to the secret store, with no chart change and no GitOps commit. Requires `dex.configSecret.create=false` and `dex.configSecret.name` equal to `secretName`, which are the defaults below. |
| dynamicConfig.base | object | `{"enablePasswordDB":true,"issuer":"https://dex.example.com","oauth2":{"skipApprovalScreen":true},"signer":{"config":{"algorithm":"RS256","keysRotationPeriod":"6h"},"type":"local"},"storage":{"config":{"inCluster":true},"type":"kubernetes"},"web":{"http":"0.0.0.0:5556"}}` | Static Dex settings that rarely change and stay in Git. Connectors and static clients listed here are kept and merged with the ones found in the store. Must not contain backticks. ref: https://github.com/dexidp/dex/blob/master/config.yaml.dist |
| dynamicConfig.base.enablePasswordDB | bool | `true` | It's a "virtual" connector (identity provider) that stores login credentials in Dex's store. NOTE: Dex can run default with this configuration, and not requires connectors, clients, or staticpassword (users) ref: https://dexidp.io/docs/connectors/local/ |
| dynamicConfig.base.issuer | string | `"https://dex.example.com"` | The public URL of the Dex server. Must match the Ingress host and TLS certificate. |
| dynamicConfig.base.oauth2 | object | `{"skipApprovalScreen":true}` | OAUth2 Configuration ref: https://dexidp.io/docs/configuration/oauth2/ |
| dynamicConfig.base.signer | object | `{"config":{"algorithm":"RS256","keysRotationPeriod":"6h"},"type":"local"}` | Signing key for Dex ref: https://dexidp.io/docs/configuration/tokens/#token-signing-configuration |
| dynamicConfig.base.storage | object | `{"config":{"inCluster":true},"type":"kubernetes"}` | The storage backend. Dex supports Kubernetes, MySQL, PostgreSQL and SQLite. ref: https://dexidp.io/docs/configuration/storage/ |
| dynamicConfig.base.web | object | `{"http":"0.0.0.0:5556"}` | HTTP Service Configuration |
| dynamicConfig.deletionPolicy | string | `"Merge"` | What ESO does when a scanned path holds no secret. `Merge` skips that source and still renders the config from `base` and the other sources, so connectors, clients and users are all optional. `Retain` (the ESO default) fails the sync with `Secret does not exist` and never creates the Secret. `Delete` removes the Secret when every source is empty, which would take Dex's config away. |
| dynamicConfig.enabled | bool | `true` | Render the ExternalSecret that generates the Dex config. Set to false to use `dex.config` and `dex.configSecret.create=true` instead. |
| dynamicConfig.refreshInterval | string | `"1m"` | Poll interval for this ExternalSecret. Also the worst-case delay before a change in the store reaches Dex. Falls back to `externalSecretDefaults.refreshInterval`. |
| dynamicConfig.secretName | string | `"dex-config"` | Name of the Secret ESO creates. It must equal `dex.configSecret.name`. |
| dynamicConfig.secretStoreRef | object | `{}` | Store override for this ExternalSecret only. Merged over `externalSecretDefaults.secretStoreRef`. |
| dynamicConfig.sources | object | `{"clients":{"nameRegexp":".*","path":"dex/clients"},"connectors":{"nameRegexp":".*","path":"dex/connectors"},"users":{"enabled":true,"nameRegexp":".*","path":"dex/users"}}` | Where the entries live, as paths relative to the store's KV mount. Each secret under a path is one JSON object. Connector: `{type, id, name, config}`. Client: `{id, name, redirectURIs, secret|secretEnv|public}`. User: `{email, username, userID, hash}` where `hash` is a bcrypt hash, never the plain password. |
| dynamicConfig.sources.clients.nameRegexp | string | `".*"` | Only secrets whose name matches this regular expression are used. |
| dynamicConfig.sources.clients.path | string | `"dex/clients"` | Path scanned for static clients. |
| dynamicConfig.sources.connectors.nameRegexp | string | `".*"` | Only secrets whose name matches this regular expression are used. |
| dynamicConfig.sources.connectors.path | string | `"dex/connectors"` | Path scanned for connectors. |
| dynamicConfig.sources.users.enabled | bool | `true` | Scan for local users (Dex `staticPasswords`). Any user found turns on `enablePasswordDB` unless `base` already sets it. Disable it to use only external connectors. |
| dynamicConfig.sources.users.nameRegexp | string | `".*"` | Only secrets whose name matches this regular expression are used. |
| dynamicConfig.sources.users.path | string | `"dex/users"` | Path scanned for local users, for example the bootstrap `admin` account. |
| externalSecretDefaults | object | `{"refreshInterval":"1h","secretStoreRef":{"kind":"SecretStore","name":""}}` | Defaults applied to every ExternalSecret this chart renders. Individual entries can override them. |
| externalSecretDefaults.refreshInterval | string | `"1h"` | How often External Secrets Operator re-reads the remote secret. |
| externalSecretDefaults.secretStoreRef | object | `{"kind":"SecretStore","name":""}` | Reference to the SecretStore that holds the remote secrets. `name` is required. Prefer a namespaced `SecretStore` in the Dex namespace, bound to a read-only OpenBao role, over a cluster-wide store. |
| externalSecretDefaults.secretStoreRef.kind | string | `"SecretStore"` | Kind of the store: `SecretStore` or `ClusterSecretStore`. |
| externalSecretDefaults.secretStoreRef.name | string | `""` | Name of the SecretStore or ClusterSecretStore. |
| externalSecrets | object | `{"env":{"data":[{"remoteRef":{"key":"dex/database","property":"password"},"secretKey":"DB_PASSWORD"}],"enabled":false,"target":{"name":"dex-env"}}}` | Extra ExternalSecrets rendered by this chart, keyed by a short name. Each entry produces one Kubernetes Secret. Use it for anything beyond the Dex config, such as a database password exposed through `dex.envFrom`. Entries accept `enabled`, `refreshInterval`, `secretStoreRef`, `target` (`name`, `creationPolicy`, `template`, ...), `data`, `dataFrom` and `annotations`, and map 1:1 onto the ExternalSecret spec. The Secret name is `target.name`, or `<dex fullname>-<key>` when not set. Values are rendered as-is (never through `tpl`), so ESO template expressions such as `{{ .password }}` need no escaping. |
| externalSecrets.env | object | `{"data":[{"remoteRef":{"key":"dex/database","property":"password"},"secretKey":"DB_PASSWORD"}],"enabled":false,"target":{"name":"dex-env"}}` | Example: environment variables for Dex, read from the store. Wire it with `dex.envFrom` and `$VAR` references or `secretEnv`. |
| externalSecretsApiVersion | string | `"external-secrets.io/v1"` | API version used for rendered ExternalSecret resources. Set `external-secrets.io/v1beta1` if your External Secrets Operator does not serve `external-secrets.io/v1` yet. |

