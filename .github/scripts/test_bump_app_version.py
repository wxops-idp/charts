"""Tests for bump_app_version.py. Run with: python3 -m unittest discover -s .github/scripts"""
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bump = load("bump_app_version")
changelog = bump.changelog

CHART_YAML = '''apiVersion: v2
name: demo
description: A demo
version: 0.1.0
appVersion: "0.5.2"
'''
CHANGELOG = '''# demo changelog

## 0.1.0 - 2026-10-19

First release.
'''


class BumpAppVersionTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "demo").mkdir()
        (self.root / "demo/Chart.yaml").write_text(CHART_YAML)
        (self.root / "demo/CHANGELOG.md").write_text(CHANGELOG)
        original = changelog.ROOT
        changelog.ROOT = self.root
        self.addCleanup(setattr, changelog, "ROOT", original)

    def run_bump(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bump.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def chart(self):
        return (self.root / "demo/Chart.yaml").read_text()

    def log(self):
        return (self.root / "demo/CHANGELOG.md").read_text()

    def test_newer_version_bumps_app_version_chart_version_and_changelog(self):
        code, out, _ = self.run_bump("demo", "v0.6.0", "--date", "2026-11-01", "--release-url", "https://example.com/r")
        self.assertEqual(code, 0)
        self.assertIn("chart_version=0.1.1", out)
        self.assertIn("old_app_version=0.5.2", out)
        self.assertIn("app_version=0.6.0", out)
        self.assertIn('appVersion: "0.6.0"', self.chart())
        self.assertIn("version: 0.1.1\n", self.chart())
        self.assertTrue(self.log().startswith("# demo changelog\n\n## 0.1.1 - 2026-11-01\n"))
        self.assertIn("Deploys the application 0.6.0 (was 0.5.2).", self.log())
        self.assertIn("[release notes](https://example.com/r)", self.log())
        self.assertIn("## 0.1.0 - 2026-10-19", self.log())

    def test_result_passes_the_changelog_check(self):
        self.run_bump("demo", "0.6.0")
        changelog.check()

    def test_minor_bump_resets_patch(self):
        self.run_bump("demo", "0.6.0", "--bump", "minor")
        self.assertIn("version: 0.2.0\n", self.chart())

    def test_same_or_older_version_changes_nothing(self):
        for version in ("0.5.2", "0.5.1", "0.4.9"):
            code, out, _ = self.run_bump("demo", version)
            self.assertEqual(code, bump.NOTHING_TO_DO, version)
            self.assertIn("nothing to do", out)
        self.assertEqual(self.chart(), CHART_YAML)
        self.assertEqual(self.log(), CHANGELOG)

    def test_second_run_with_the_same_version_is_a_no_op(self):
        self.run_bump("demo", "0.6.0")
        code, _, _ = self.run_bump("demo", "0.6.0")
        self.assertEqual(code, bump.NOTHING_TO_DO)
        self.assertEqual(self.log().count("## 0.1.1"), 1)

    def test_numeric_comparison_not_string_comparison(self):
        (self.root / "demo/Chart.yaml").write_text(CHART_YAML.replace('"0.5.2"', '"0.9.0"'))
        code, _, _ = self.run_bump("demo", "0.10.0")
        self.assertEqual(code, 0)
        self.assertIn('appVersion: "0.10.0"', self.chart())

    def test_prerelease_and_garbage_versions_are_refused(self):
        for version in ("0.6.0-rc.1", "latest", "0.6"):
            code, _, err = self.run_bump("demo", version)
            self.assertEqual(code, 1, version)
            self.assertIn("not a stable", err)
        self.assertEqual(self.chart(), CHART_YAML)

    def test_unquoted_app_version_keeps_its_style(self):
        (self.root / "demo/Chart.yaml").write_text(CHART_YAML.replace('"0.5.2"', "0.5.2"))
        self.run_bump("demo", "0.6.0")
        self.assertIn("appVersion: 0.6.0\n", self.chart())

    def test_unknown_chart_is_an_error(self):
        code, _, err = self.run_bump("missing", "0.6.0")
        self.assertEqual(code, 1)
        self.assertIn("not a chart", err)

    def test_a_changelog_without_the_title_is_refused_and_nothing_is_written(self):
        (self.root / "demo/CHANGELOG.md").write_text("## 0.1.0 - 2026-10-19\n\nFirst release.\n")
        code, _, err = self.run_bump("demo", "0.6.0")
        self.assertEqual(code, 1)
        self.assertIn("must start with", err)
        self.assertEqual(self.chart(), CHART_YAML)


if __name__ == "__main__":
    unittest.main()
