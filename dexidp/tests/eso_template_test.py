#!/usr/bin/env python3
"""Evaluate files/config.yaml.tmpl, the template External Secrets Operator runs, against sample store entries.

helm-unittest only sees the ExternalSecret that Helm renders, where this template is just text. This test runs
the template itself with the same engine settings as ESO (see eso-render/main.go: text/template, sprig,
`missingkey=error`) and the entries from eso_template_cases.json as the ESO data, then checks the Dex config it
produces or the error it raises.

`helm template` is not used because it is more lenient than ESO: a missing map key renders empty in Helm and is an
error in ESO, which is how a template that passed here once failed on the cluster.

Usage: python3 dexidp/tests/eso_template_test.py        (needs Go on PATH, no cluster)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "files" / "config.yaml.tmpl"
CASES = HERE / "eso_template_cases.json"
RENDERER_SRC = HERE / "eso-render"

DEFAULT_BASE = {
    "issuer": "https://dex.example.com",
    "storage": {"type": "kubernetes", "config": {"inCluster": True}},
    "web": {"http": "0.0.0.0:5556"},
}


def build_renderer(directory: Path) -> Path:
    binary = directory / "eso-render"
    subprocess.run(["go", "build", "-o", str(binary), "."], cwd=RENDERER_SRC, check=True)
    return binary


def render(binary: Path, work: Path, base: dict, entries: dict) -> subprocess.CompletedProcess:
    # The chart does the same replacement in templates/externalsecret-config.yaml.
    body = TEMPLATE.read_text().replace("__BASE_JSON__", json.dumps(base, separators=(",", ":")))
    template_file = work / "config.yaml.tmpl"
    data_file = work / "data.json"
    template_file.write_text(body)
    data_file.write_text(json.dumps(entries))
    return subprocess.run([str(binary), str(template_file), str(data_file)], capture_output=True, text=True)


def main() -> int:
    failures = 0
    outputs: dict = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        binary = build_renderer(work)
        for case in json.loads(CASES.read_text()):
            result = render(binary, work, case.get("base", DEFAULT_BASE), case.get("input", {}))
            problems = []
            if "error" in case:
                if result.returncode == 0:
                    problems.append(f"expected an error containing {case['error']!r}, but it rendered")
                elif case["error"] not in result.stderr:
                    problems.append(f"expected error containing {case['error']!r}, got: {result.stderr.strip()}")
            else:
                if result.returncode != 0:
                    problems.append(f"expected it to render, got: {result.stderr.strip()}")
                for want in case.get("contains", []):
                    if want not in result.stdout:
                        problems.append(f"output is missing {want!r}")
                for unwanted in case.get("not_contains", []):
                    if unwanted in result.stdout:
                        problems.append(f"output must not contain {unwanted!r}")
                # Two inputs that mean the same thing (a native list and the same list as a JSON string)
                # must produce exactly the same Dex config.
                if "same_output_as" in case:
                    other = outputs.get(case["same_output_as"])
                    if other is None:
                        problems.append(f"same_output_as {case['same_output_as']!r} must name an earlier passing case")
                    elif other != result.stdout:
                        problems.append(f"output differs from the one for {case['same_output_as']!r}")
                outputs[case["name"]] = result.stdout
            status = "FAIL" if problems else "PASS"
            print(f"{status}  {case['name']}")
            for problem in problems:
                print(f"        {problem}")
            failures += bool(problems)
    print(f"\n{failures} failed" if failures else "\nall cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
