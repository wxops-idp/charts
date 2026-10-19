#!/usr/bin/env python3
"""Point a chart at a newer application release: bump `appVersion`, bump the chart `version`, add a changelog entry.

Used by .github/workflows/bump-portal.yaml, which opens a pull request with the result. A person still reviews and
merges it, and chart-releaser then publishes the new chart version.

Usage:
    bump_app_version.py <chart> <app-version> [--bump patch|minor] [--release-url URL] [--date YYYY-MM-DD]

Prints `chart_version=`, `old_app_version=` and `app_version=` lines, ready to append to $GITHUB_OUTPUT.

Exit codes: 0 changed, 1 error, 10 nothing to do (the chart already deploys that version or a newer one).
"""
import argparse
import importlib.util
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reuse the changelog tooling, so the files written here pass `changelog.py check` by construction.
_spec = importlib.util.spec_from_file_location("changelog", Path(__file__).with_name("changelog.py"))
changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changelog)

NOTHING_TO_DO = 10
STABLE_RE = re.compile(r"^\d+\.\d+\.\d+$")
APP_VERSION_RE = re.compile(r"^(appVersion:\s*)([\"']?)([^\"'\s#]+)([\"']?)(.*)$", re.MULTILINE)
VERSION_RE = re.compile(r"^(version:\s*)([\"']?)(\d+)\.(\d+)\.(\d+)([\"']?)(.*)$", re.MULTILINE)


def bump_chart_version(chart_yaml: str, how: str) -> tuple:
    match = VERSION_RE.search(chart_yaml)
    if not match:
        raise changelog.ChangelogError("Chart.yaml `version` must be a plain MAJOR.MINOR.PATCH to be bumped")
    major, minor, patch = int(match[3]), int(match[4]), int(match[5])
    major_minor_patch = (major, minor + 1, 0) if how == "minor" else (major, minor, patch + 1)
    new = ".".join(str(n) for n in major_minor_patch)
    line = f"{match[1]}{match[2]}{new}{match[6]}{match[7]}"
    return chart_yaml[: match.start()] + line + chart_yaml[match.end():], new


def set_app_version(chart_yaml: str, new: str) -> tuple:
    match = APP_VERSION_RE.search(chart_yaml)
    if not match:
        raise changelog.ChangelogError("Chart.yaml has no top-level `appVersion`")
    line = f"{match[1]}{match[2]}{new}{match[4]}{match[5]}"
    return chart_yaml[: match.start()] + line + chart_yaml[match.end():], match[3]


def add_changelog_entry(text: str, chart: str, chart_version: str, old: str, new: str, release_url: str, day: str) -> str:
    sentence = f"Deploys the application {new} (was {old})."
    if release_url:
        sentence += f" See the [release notes]({release_url}) for what changed."
    section = f"## {chart_version} - {day}\n\n{sentence}\n"
    title = f"# {chart} changelog\n"
    if not text.startswith(title):
        raise changelog.ChangelogError(f"{chart}/CHANGELOG.md must start with `{title.strip()}`")
    rest = text[len(title):].lstrip("\n")
    return f"{title}\n{section}\n{rest}"


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("chart")
    parser.add_argument("app_version")
    parser.add_argument("--bump", choices=["patch", "minor"], default="patch", help="how to bump the chart version")
    parser.add_argument("--release-url", default="")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    args = parser.parse_args(argv)

    new = args.app_version.removeprefix("v")
    try:
        if not STABLE_RE.match(new):
            raise changelog.ChangelogError(f"`{new}` is not a stable MAJOR.MINOR.PATCH version")
        chart_dir = changelog.ROOT / args.chart
        chart_file = chart_dir / "Chart.yaml"
        if not chart_file.exists():
            raise changelog.ChangelogError(f"`{args.chart}` is not a chart (no {args.chart}/Chart.yaml)")

        current = changelog.chart_field(chart_dir, "appVersion")
        if STABLE_RE.match(current) and changelog.version_key(new) <= changelog.version_key(current):
            print(f"{args.chart} already deploys {current}, nothing to do for {new}")
            return NOTHING_TO_DO

        chart_yaml, old = set_app_version(chart_file.read_text(), new)
        chart_yaml, chart_version = bump_chart_version(chart_yaml, args.bump)
        log_file = chart_dir / "CHANGELOG.md"
        log = add_changelog_entry(
            log_file.read_text(), args.chart, chart_version, old, new, args.release_url, args.date
        )
        chart_file.write_text(chart_yaml)
        log_file.write_text(log)
        changelog.validate(chart_dir)
    except changelog.ChangelogError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"chart_version={chart_version}")
    print(f"old_app_version={old}")
    print(f"app_version={new}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
