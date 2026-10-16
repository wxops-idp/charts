// eso-render evaluates a template the way External Secrets Operator (template engine v2) does, so the
// chart's config template can be tested without a cluster.
//
// It matches runtime/template/v2/template.go in ESO v1.2.1: text/template with Option("missingkey=error"),
// the sprig text function map without env and expandenv, and a map[string]string as the data.
// `helm template` is more lenient (a missing map key renders empty), so it cannot be used for this.
//
// Usage: eso-render <template-file> <data.json>   (data.json is an object of string values)
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"text/template"

	"github.com/Masterminds/sprig/v3"
	"sigs.k8s.io/yaml"
)

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: eso-render <template-file> <data.json>")
		os.Exit(2)
	}
	tmpl, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	raw, err := os.ReadFile(os.Args[2])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	data := map[string]string{}
	if err := json.Unmarshal(raw, &data); err != nil {
		fmt.Fprintln(os.Stderr, "data.json must be an object of strings:", err)
		os.Exit(2)
	}

	funcs := sprig.TxtFuncMap()
	delete(funcs, "env")
	delete(funcs, "expandenv")
	// The ESO functions the chart template uses (runtime/template/v2/yaml.go). The PKCS12, PEM and JWK helpers
	// are not registered here because the template does not call them.
	funcs["toYaml"] = func(v any) string {
		out, err := yaml.Marshal(v)
		if err != nil {
			return ""
		}
		return strings.TrimSuffix(string(out), "\n")
	}
	funcs["fromYaml"] = func(s string) map[string]any {
		m := map[string]any{}
		if err := yaml.Unmarshal([]byte(s), &m); err != nil {
			m["Error"] = err.Error()
		}
		return m
	}

	t, err := template.New("config.yaml").Option("missingkey=error").Funcs(funcs).Parse(string(tmpl))
	if err != nil {
		fmt.Fprintln(os.Stderr, "could not parse template:", err)
		os.Exit(1)
	}
	if err := t.Execute(os.Stdout, data); err != nil {
		fmt.Fprintln(os.Stderr, "could not execute template:", err)
		os.Exit(1)
	}
}
