#!/usr/bin/env python3
"""Check and assemble the chart changelogs. It never writes entries, those stay hand-written.

Every chart (a top-level directory with a Chart.yaml) keeps its own `<chart>/CHANGELOG.md`, newest section first:

    # dexidp changelog

    ## 0.1.1 - 2026-10-16

    ### Added
    - ...

    ## 0.1.0 - 2026-10-05
    - First release.

Commands:
    check           Fail unless each chart's newest section matches the `version` in its Chart.yaml.
    generate        Rewrite the chart table in the root README.md, between the charts:start/end markers.
    sync            check, then generate. This is what pre-commit runs.
    notes <chart>   Print the newest section of a chart. The release workflow packages it as the release notes.

Only the standard library is used, so it runs anywhere Python 3 does.
"""
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .github/scripts/changelog.py -> repository root
ROOT_README = ROOT / "README.md"

# The root README is also published as the README of the gh-pages branch (the chart site), where there are no
# chart directories, so the table links to each chart by absolute URL.
CHART_URL = "https://github.com/wxops-idp/charts/tree/main/{chart}"
FILE_URL = "https://github.com/wxops-idp/charts/blob/main/{chart}/{file}"
TABLE_START = "<!-- charts:start -->"
TABLE_END = "<!-- charts:end -->"

HEADING_RE = re.compile(r"^## (?P<version>\S+) - (?P<date>\d{4}-\d{2}-\d{2})\s*$")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


class ChangelogError(Exception):
    pass


def charts() -> list:
    return sorted(p.parent for p in ROOT.glob("*/Chart.yaml"))


def chart_field(chart: Path, field: str) -> str:
    """Read a top-level scalar from Chart.yaml, the same way the lint workflow does."""
    for line in (chart / "Chart.yaml").read_text().splitlines():
        match = re.match(rf"^{field}:\s*[\"']?([^\"'\s#]+)", line)
        if match:
            return match.group(1)
    raise ChangelogError(f"{chart.name}/Chart.yaml has no top-level `{field}`")


def chart_description(chart: Path) -> str:
    """The one-line `description` of Chart.yaml, made safe for a Markdown table cell."""
    for line in (chart / "Chart.yaml").read_text().splitlines():
        match = re.match(r"^description:\s*(.*?)\s*$", line)
        if not match:
            continue
        value = match.group(1)
        if value[:1] in (">", "|") or not value:
            raise ChangelogError(f"{chart.name}/Chart.yaml: `description` must be a single line")
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value.replace("|", "\\|")
    raise ChangelogError(f"{chart.name}/Chart.yaml has no top-level `description`")


def version_key(version: str) -> tuple:
    """Sort key for semver, a release sorts above its own prereleases."""
    match = SEMVER_RE.match(version)
    if not match:
        raise ChangelogError(f"`{version}` is not a semantic version (expected MAJOR.MINOR.PATCH)")
    major, minor, patch, pre = match.groups()
    return (int(major), int(minor), int(patch), 1 if pre is None else 0, pre or "")


def sections(chart: Path) -> list:
    """Parse <chart>/CHANGELOG.md into [{version, date, body}], in file order."""
    path = chart / "CHANGELOG.md"
    if not path.exists():
        raise ChangelogError(
            f"{chart.name}/CHANGELOG.md is missing. Add it with a `## {chart_field(chart, 'version')} - YYYY-MM-DD` section"
        )
    found = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.startswith("## "):
            if found:
                found[-1]["body"].append(line)
            continue
        match = HEADING_RE.match(line)
        if not match:
            raise ChangelogError(
                f"{chart.name}/CHANGELOG.md:{number}: `{line}` is not `## <version> - YYYY-MM-DD`"
            )
        try:
            date.fromisoformat(match["date"])
        except ValueError:
            raise ChangelogError(f"{chart.name}/CHANGELOG.md:{number}: `{match['date']}` is not a real date") from None
        version_key(match["version"])
        found.append({"version": match["version"], "date": match["date"], "line": number, "body": []})
    for section in found:
        section["body"] = "\n".join(section["body"]).strip("\n")
    return found


def validate(chart: Path) -> list:
    found = sections(chart)
    current = chart_field(chart, "version")
    name = chart.name
    if not found:
        raise ChangelogError(f"{name}/CHANGELOG.md has no sections. Add `## {current} - YYYY-MM-DD`")

    seen = set()
    for section in found:
        if section["version"] in seen:
            raise ChangelogError(f"{name}/CHANGELOG.md:{section['line']}: version {section['version']} appears twice")
        seen.add(section["version"])
    keys = [version_key(s["version"]) for s in found]
    if keys != sorted(keys, reverse=True):
        raise ChangelogError(f"{name}/CHANGELOG.md: sections must be newest first (highest version at the top)")

    top = found[0]["version"]
    if top != current:
        if current not in seen:
            raise ChangelogError(
                f"{name}/Chart.yaml is at {current} but {name}/CHANGELOG.md has no `## {current} - YYYY-MM-DD` section. "
                f"Add one at the top (newest section is {top})"
            )
        raise ChangelogError(
            f"{name}/CHANGELOG.md starts with {top} but {name}/Chart.yaml is at {current}. "
            f"Bump `version` in Chart.yaml, or move the {current} section to the top"
        )
    if not found[0]["body"].strip():
        raise ChangelogError(f"{name}/CHANGELOG.md: the {current} section is empty, say what changed")
    return found


def check() -> None:
    problems = []
    names = charts()
    if not names:
        raise ChangelogError("no chart found (no */Chart.yaml)")
    for chart in names:
        try:
            validate(chart)
        except ChangelogError as error:
            problems.append(str(error))
    if problems:
        raise ChangelogError("\n".join(problems))


ROW_NAME_RE = re.compile(r"^\|\s*\[`(?P<name>[^`]+)`\]")
UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def existing_rows(block: str) -> dict:
    """{chart name: its "What it does" cell} from the table now in the README, in row order.

    That column is the only hand-written one, so it is kept as written. Everything else is regenerated.
    """
    rows = {}
    for line in block.splitlines():
        match = ROW_NAME_RE.match(line)
        if not match:
            continue
        cells = UNESCAPED_PIPE_RE.split(line)
        if len(cells) > 2 and cells[2].strip():
            rows[match["name"]] = cells[2].strip()
    return rows


def render_table(existing: dict) -> str:
    by_name = {chart.name: chart for chart in charts()}
    # Rows already in the README keep their order, new charts follow alphabetically.
    ordered = [n for n in existing if n in by_name] + sorted(n for n in by_name if n not in existing)
    rows = []
    for name in ordered:
        chart = by_name[name]
        top = validate(chart)[0]
        docs = (
            f"[README]({FILE_URL.format(chart=name, file='README.md')}) · "
            f"[Changelog]({FILE_URL.format(chart=name, file='CHANGELOG.md')})"
        )
        what = existing.get(name) or chart_description(chart)
        rows.append(
            f"| [`{name}`]({CHART_URL.format(chart=name)}) | {what} | {top['version']} "
            f"| {chart_field(chart, 'appVersion')} | {top['date']} | {docs} |"
        )
    return "\n".join(
        [
            "<!-- Generated by .github/scripts/changelog.py. Version, app version, release date and links come from "
            "<chart>/Chart.yaml and <chart>/CHANGELOG.md. \"What it does\" is the only column to edit here. -->",
            "",
            "| Chart | What it does | Version | App version | Released | Docs |",
            "| --- | --- | --- | --- | --- | --- |",
            *rows,
        ]
    )


def generate() -> bool:
    """Rewrite the table between the markers in the root README.md. Returns True when the file changed."""
    text = ROOT_README.read_text()
    start, end = text.find(TABLE_START), text.find(TABLE_END)
    if start == -1 or end == -1 or end < start:
        raise ChangelogError(
            f"README.md needs the markers {TABLE_START} and {TABLE_END} (in that order) around the chart table"
        )
    head = text[: start + len(TABLE_START)]
    block = text[start + len(TABLE_START) : end]
    new = f"{head}\n{render_table(existing_rows(block))}\n{text[end:]}"
    if new == text:
        return False
    ROOT_README.write_text(new)
    return True


def notes(chart_name: str) -> str:
    chart = ROOT / chart_name
    if not (chart / "Chart.yaml").exists():
        raise ChangelogError(f"`{chart_name}` is not a chart (no {chart_name}/Chart.yaml)")
    top = validate(chart)[0]
    return top["body"] + "\n"


def main(argv: list) -> int:
    command = argv[1] if len(argv) > 1 else ""
    try:
        if command == "check":
            check()
            print("changelogs ok")
        elif command == "generate":
            check()
            print("README.md updated" if generate() else "README.md is up to date")
        elif command == "sync":
            check()
            if generate():
                print("README.md version table was regenerated, stage it")
        elif command == "notes" and len(argv) == 3:
            sys.stdout.write(notes(argv[2]))
        else:
            print(__doc__.strip().split("\n\n")[0] + "\n\nusage: changelog.py check|generate|sync|notes <chart>", file=sys.stderr)
            return 2
    except ChangelogError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
