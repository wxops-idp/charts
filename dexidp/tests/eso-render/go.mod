module eso-render

go 1.22

require (
	github.com/Masterminds/sprig/v3 v3.3.0
	sigs.k8s.io/yaml v1.6.0
)

require (
	dario.cat/mergo v1.0.0 // indirect
	github.com/Masterminds/goutils v1.1.1 // indirect
	github.com/Masterminds/semver/v3 v3.2.0 // indirect
	github.com/google/uuid v1.1.1 // indirect
	github.com/huandu/xstrings v1.3.3 // indirect
	github.com/mitchellh/copystructure v1.0.0 // indirect
	github.com/mitchellh/reflectwalk v1.0.0 // indirect
	github.com/shopspring/decimal v1.2.0 // indirect
	github.com/spf13/cast v1.3.1 // indirect
	go.yaml.in/yaml/v2 v2.4.2 // indirect
	golang.org/x/crypto v0.3.0 // indirect
)

// External Secrets Operator v1.2.1 builds its template functions from this fork.
replace github.com/Masterminds/sprig/v3 => github.com/external-secrets/sprig/v3 v3.3.0
