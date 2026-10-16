# dexidp changelog

## 0.1.1 - 2026-10-16

Aligns the dynamic config with what the W'xOps core side pushes to the secret store. Upgrade from 0.1.0 needs no
value changes. Dex 2.45.1, upstream dex chart 0.25.2.

### Added
- `dynamicConfig.deletionPolicy` (default `Merge`). A scanned path with no secret is skipped, so connectors, clients
  and users are all optional.
- `groups` (users) and `redirectURIs` (clients) are accepted as a list or as a JSON-encoded string, and both produce
  the same Dex config.
- `signer` (local, RS256, 6h rotation) and `enablePasswordDB: true` in the default `dynamicConfig.base`.
- `dexidp/tests/eso_template_test.py`, which runs the ESO template with ESO's own engine settings, plus cases for
  every validation.

### Changed
- An empty connectors, clients or users path no longer fails the sync with `Secret does not exist`.
- `groups` and `redirectURIs` must be lists of strings. A plain string, an object or a non-string entry fails the
  sync and names the secret.
- Invalid JSON in an entry is reported as invalid JSON, not as a missing field.

### Fixed
- `find` returned the full path as the key (`connector_dex/connectors/gitea`), which ESO rejects. Only the secret
  name, the last path segment, is used now.
- A base without `connectors`, `staticClients` or `staticPasswords` failed under ESO's `missingkey=error`.

### For core
- The name of a secret under `dex/connectors`, `dex/clients` and `dex/users` is its key, the path is not part of it.
- Push lists as JSON arrays or as JSON-encoded strings, both work.

## 0.1.0 - 2026-10-05

First release. Wraps the upstream Dex chart and builds Dex's `config.yaml` with External Secrets Operator from
connectors, clients and users stored in a secret backend such as OpenBao.
