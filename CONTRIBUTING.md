# Contributing

Every pull request to `main` runs `.github/workflows/lint-test.yaml`. Releases are cut from `main` by `release.yaml`, so what passes here is what ships.

## What the checks do

| Check | What it catches |
| --- | --- |
| `ct lint` | `helm lint`, YAML style of `Chart.yaml` and `values.yaml`, and a missing `version` bump on a changed chart |
| `helm unittest` | The expectations in `<chart>/tests/`, including every required parameter |
| Render + `kubeconform` | `values-test.yaml` renders, and the manifests are valid against Kubernetes and CRD schemas |
| `helm-docs` | `README.md` matches `README.md.gotmpl` and the `# --` comments in `values.yaml` |

Run them locally before pushing:

```bash
helm dependency build dexidp          # once, and after changing dependencies
helm unittest dexidp pinniped
helm template t dexidp -f dexidp/values-test.yaml | kubeconform -strict -ignore-missing-schemas -summary
ct lint --config ct.yaml              # needs ct, yamllint and yamale
helm-docs --chart-search-root=. --template-files=README.md.gotmpl
```

## Changing a chart

1. **Bump `version` in `Chart.yaml`.** chart-releaser skips a chart whose version already has a release, so without a bump the change never ships. Use a patch bump for fixes, a minor bump for new values, and a major bump for anything that breaks an existing install. The check only applies once the version on `main` has a release tag (`<chart>-<version>`), so a version that has not shipped yet, such as the first `0.1.0`, can still change without a bump.
2. **Update `values-test.yaml`** when you add a feature that needs values to render. It is the baseline the tests and `kubeconform` use, so it should render the chart with its main features on.
3. **Run `helm-docs`** and commit the regenerated `README.md`.

## Required parameters and core settings

A parameter is *required* when the chart cannot produce a working install without it (an issuer, a hostname, a secret store). Required parameters are enforced in the templates with `required` or `fail`, and each one has an expectation in `<chart>/tests/`:

```yaml
- it: fails when the FederationDomain has no issuer
  template: templates/supervisor/pinniped-extras.yaml
  set:
    supervisor.federationDomain.issuer: ""
  asserts:
    - failedTemplate:
        errorMessage: "supervisor.federationDomain.issuer is required when federationDomain.create=true"
```

When a PR changes a core setting, it must do all of the following in the same PR:

- **Adding a required parameter:** add the `required` / `fail` with a message that names the value and when it applies, add a failing case like the one above, and add the value to `values-test.yaml` (and to `dexidp/ci/default-values.yaml` if the default install needs it).
- **Removing or renaming one:** update or delete its test. A test that still passes against a removed guard means the guard was never covered.
- **Making an optional value required (or the other way round):** that changes what existing installs must set, so bump the major version and say so in the PR description.

Reviewers should treat a change to `tests/` that loosens an expectation as a change to the chart's contract.
