# W'xOps Service and Resources Helm Charts

[![Lint and Test Charts](https://github.com/wxops-idp/charts/actions/workflows/lint-test.yaml/badge.svg?branch=main)](https://github.com/wxops-idp/charts/actions/workflows/lint-test.yaml)
[![Release Charts](https://github.com/wxops-idp/charts/actions/workflows/release.yaml/badge.svg?branch=main)](https://github.com/wxops-idp/charts/actions/workflows/release.yaml)
[![Latest release](https://img.shields.io/github/v/release/wxops-idp/charts?include_prereleases&sort=semver)](https://github.com/wxops-idp/charts/releases)
[![License](https://img.shields.io/github/license/wxops-idp/charts)](LICENSE)
[![Helm](https://img.shields.io/badge/Helm-3-0F1689?logo=helm&logoColor=white)](https://helm.sh/)

Helm charts for the W'xOps identity stack: sign in to Kubernetes with Pinniped, and give the W'xOps ecosystem OIDC sign-in against your source control through Dex.

## Charts

| Chart | What it does | Docs |
| --- | --- | --- |
| [`pinniped`](pinniped) | Kubernetes authentication through the Pinniped Supervisor and Concierge, with Traefik, NGINX, Gateway API or LoadBalancer exposure and optional cert-manager TLS | [README](pinniped/README.md) |
| [`dexidp`](dexidp) | A thin wrapper around the upstream Dex chart. External Secrets Operator builds Dex's `config.yaml` from a secret backend such as OpenBao, so connectors and clients change without a chart change | [README](dexidp/README.md) |

Dex can be the identity provider behind Pinniped. See "Using Dex with Pinniped" in the [dexidp README](dexidp/README.md).

## Quick start

```bash
helm repo add wxops https://charts.wxops.cloud
helm repo update
helm search repo wxops
```

Install a chart with its README as the guide. `dexidp` needs a secret store name to render, and `pinniped` needs an issuer or a hostname once you turn on a feature that uses one. A missing value fails the install with a message that names it, not with a half-working release.

```bash
helm install pinniped wxops/pinniped --dry-run --debug -f my-values.yaml   # check first
helm install dex wxops/dexidp -n idp --create-namespace \
  --set externalSecretDefaults.secretStoreRef.name=dex-openbao
```

## How these charts are checked

Every pull request runs [`lint-test.yaml`](.github/workflows/lint-test.yaml), and a chart is only released from `main` after it passes:

- **Lint:** `helm lint` and YAML style through chart-testing, plus a version bump for any chart that has already been released.
- **Required parameters:** unit tests assert that each required value fails the render with a clear message. They live in `<chart>/tests/`.
- **Render and schema:** each chart is rendered with its `values-test.yaml` and the manifests are validated with kubeconform against the Kubernetes and CRD schemas.
- **Docs:** the chart READMEs are regenerated with helm-docs and must match.

What this does not cover: the charts are rendered and validated, not installed on a cluster in CI. The [dexidp README](dexidp/README.md) lists what has not been verified against a real External Secrets Operator and OpenBao. Test in a non-production cluster first.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to run the checks locally and what a pull request that changes a required parameter must include.

## License

Apache License 2.0, see [LICENSE](LICENSE).
