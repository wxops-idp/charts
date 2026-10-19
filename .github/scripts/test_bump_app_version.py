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
appVersion: "v0.5.2"
'''
CHANGELOG = '''# demo changelog

## 0.1.0 - 2026-10-19

First release.
'''
VALUES = '''replicaCount: 1

image:
  repository: ghcr.io/example/demo
  # empty means appVersion
  tag: ""
  pullPolicy: IfNotPresent

other:
  tag: "leave-me"
'''


class BumpAppVersionTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "demo").mkdir()
        (self.root / "demo/Chart.yaml").write_text(CHART_YAML)
        (self.root / "demo/CHANGELOG.md").write_text(CHANGELOG)
        (self.root / "demo/values.yaml").write_text(VALUES)
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

    def values(self):
        return (self.root / "demo/values.yaml").read_text()

    def set_chart(self, **replacements):
        text = CHART_YAML
        for old, new in replacements.items():
            text = text.replace(old.replace("_", " "), new)
        (self.root / "demo/Chart.yaml").write_text(text)

    # --- what gets written

    def test_newer_version_sets_app_version_exactly_as_given_and_bumps_chart_and_changelog(self):
        code, out, _ = self.run_bump("demo", "v0.6.0", "--date", "2026-11-01", "--release-url", "https://example.com/r")
        self.assertEqual(code, 0)
        self.assertIn("chart_version=0.1.1", out)
        self.assertIn("old_app_version=v0.5.2", out)
        self.assertIn("app_version=v0.6.0", out)
        self.assertIn('appVersion: "v0.6.0"', self.chart())
        self.assertIn("version: 0.1.1\n", self.chart())
        self.assertTrue(self.log().startswith("# demo changelog\n\n## 0.1.1 - 2026-11-01\n"))
        self.assertIn("Deploys the application v0.6.0 (was v0.5.2).", self.log())
        self.assertIn("[release notes](https://example.com/r)", self.log())
        self.assertIn("## 0.1.0 - 2026-10-19", self.log())

    def test_no_prefix_is_added_or_removed(self):
        self.run_bump("demo", "0.6.0")
        self.assertIn('appVersion: "0.6.0"', self.chart())

    def test_unquoted_app_version_keeps_its_style(self):
        (self.root / "demo/Chart.yaml").write_text(CHART_YAML.replace('"v0.5.2"', "v0.5.2"))
        self.run_bump("demo", "v0.6.0")
        self.assertIn("appVersion: v0.6.0\n", self.chart())

    def test_values_yaml_is_never_touched(self):
        self.run_bump("demo", "v0.6.0")
        self.assertEqual(self.values(), VALUES)

    def test_result_passes_the_changelog_check(self):
        self.run_bump("demo", "v0.6.0")
        changelog.check()

    def test_minor_bump_resets_patch(self):
        self.run_bump("demo", "v0.6.0", "--bump", "minor")
        self.assertIn("version: 0.2.0\n", self.chart())

    # --- when there is nothing to do

    def test_same_or_older_version_changes_nothing_with_or_without_the_v(self):
        for version in ("v0.5.2", "0.5.2", "v0.5.1", "0.4.9"):
            code, out, _ = self.run_bump("demo", version)
            self.assertEqual(code, bump.NOTHING_TO_DO, version)
            self.assertIn("nothing to do", out)
        self.assertEqual(self.chart(), CHART_YAML)
        self.assertEqual(self.log(), CHANGELOG)

    def test_second_run_with_the_same_version_is_a_no_op(self):
        self.run_bump("demo", "v0.6.0")
        code, _, _ = self.run_bump("demo", "v0.6.0")
        self.assertEqual(code, bump.NOTHING_TO_DO)
        self.assertEqual(self.log().count("## 0.1.1"), 1)

    def test_numeric_comparison_not_string_comparison(self):
        (self.root / "demo/Chart.yaml").write_text(CHART_YAML.replace("v0.5.2", "v0.9.0"))
        code, _, _ = self.run_bump("demo", "v0.10.0")
        self.assertEqual(code, 0)
        self.assertIn('appVersion: "v0.10.0"', self.chart())

    def test_the_tag_style_may_change_when_the_registry_changes_it(self):
        code, _, _ = self.run_bump("demo", "0.6.0")
        self.assertEqual(code, 0)
        self.assertIn('appVersion: "0.6.0"', self.chart())

    # --- refusals, nothing is written

    def test_prerelease_and_garbage_versions_are_refused(self):
        for version in ("v0.6.0-rc.1", "latest", "0.6", "vv0.6.0"):
            code, _, err = self.run_bump("demo", version)
            self.assertEqual(code, 1, version)
            self.assertIn("not a stable version", err)
        self.assertEqual(self.chart(), CHART_YAML)

    def test_a_pinned_image_tag_blocks_the_bump(self):
        (self.root / "demo/values.yaml").write_text(VALUES.replace('tag: ""', 'tag: "v0.5.2"'))
        code, _, err = self.run_bump("demo", "v0.6.0")
        self.assertEqual(code, 1)
        self.assertIn("pins image.tag to `v0.5.2`", err)
        self.assertEqual(self.chart(), CHART_YAML)
        self.assertEqual(self.log(), CHANGELOG)

    def test_other_tag_keys_and_a_missing_values_file_do_not_block(self):
        self.assertEqual(bump.pinned_image_tag(VALUES), "")
        (self.root / "demo/values.yaml").unlink()
        code, _, _ = self.run_bump("demo", "v0.6.0")
        self.assertEqual(code, 0)

    def test_only_the_top_level_image_block_counts_as_a_pin(self):
        self.assertEqual(bump.pinned_image_tag("sidecar:\n  tag: keep\nimage:\n  repository: x\n  tag: v1.0.0\n"), "v1.0.0")
        self.assertEqual(bump.pinned_image_tag("sidecar:\n  tag: keep\nimage:\n  repository: x\n"), "")

    def test_unknown_chart_is_an_error(self):
        code, _, err = self.run_bump("missing", "v0.6.0")
        self.assertEqual(code, 1)
        self.assertIn("not a chart", err)

    def test_a_changelog_without_the_title_is_refused_and_nothing_is_written(self):
        (self.root / "demo/CHANGELOG.md").write_text("## 0.1.0 - 2026-10-19\n\nFirst release.\n")
        code, _, err = self.run_bump("demo", "v0.6.0")
        self.assertEqual(code, 1)
        self.assertIn("must start with", err)
        self.assertEqual(self.chart(), CHART_YAML)


class PortalChartConsistencyTest(unittest.TestCase):
    """The real wxops-portal chart: the image follows appVersion, which is the exact tag in the registry."""

    chart_dir = HERE.parents[1] / "wxops-portal"

    def setUp(self):
        if not self.chart_dir.exists():
            self.skipTest("no wxops-portal chart")

    def test_values_do_not_pin_an_image_tag(self):
        pinned = bump.pinned_image_tag((self.chart_dir / "values.yaml").read_text())
        app_version = changelog.chart_field(self.chart_dir, "appVersion")
        self.assertIn(pinned, ("", app_version), f"image.tag {pinned!r} would override appVersion {app_version!r}")

    def test_app_version_is_a_stable_version(self):
        app_version = changelog.chart_field(self.chart_dir, "appVersion")
        self.assertRegex(app_version, r"^v?\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
