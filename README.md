# Skyward-to-Eduphoria Role Importer

A menu-driven command-line tool that compares effective-dated Skyward
assignment data day-over-day and generates the Eduphoria Management role
additions and removals needed to keep application access correct — for
Strive Evaluation, Strive Professional Learning, Formspace, Forethought, and
Aware.

When someone's Skyward assignment changes — a new hire, a campus transfer, a
termination, a role change — their Eduphoria-connected application access
needs to change with it. Doing that by hand, every day, across every
assignment change, doesn't scale. This tool automates the diff and produces
an import-ready CSV, with an interactive prompt the first time it sees a new
Skyward assignment type asking which Eduphoria role(s) it should map to (so
the mapping only has to be taught once, not hardcoded).

## What it does

- Auto-detects the Skyward export's columns (employee identifier, assignment
  type, building code, start/end dates, display name) against a candidate
  list, with an interactive picker as a fallback.
- Computes each employee's *active* assignment/building pairs on a given
  date from their effective date ranges, and diffs that against the prior
  day to find who's entering or leaving a role.
- The first time it sees an unmapped assignment type, it asks whether that
  assignment needs an Eduphoria role at all (no for substitutes, aides,
  etc.) and, if so, which role(s) and application(s) it maps to — then
  remembers the answer permanently in `role_memory.json`.
- Detects missed run days and offers to catch up the diff across all of
  them, not just today.
- Ships with a self-update command (`--update`) that pulls the latest
  script and launcher files from this repository's `main` branch, and an
  optional "add a desktop shortcut" helper for Windows, macOS, and Linux.

## Getting started

**Requirements:** Python 3.8+ and the packages in `requirements.txt`
(`pandas`; installed automatically by the launcher scripts, or manually with
`pip install -r requirements.txt`).

```bash
# macOS / Linux
bash LAUNCH_MAC_LINUX.sh

# Windows
LAUNCH_WINDOWS.bat
```

Or run the script directly once dependencies are installed:

```bash
python skyward_to_eduphoria.py [--date YYYY-MM-DD] [--catchup] [--update]
```

Drop your Skyward export (CSV/XLSX) in the same folder and follow the menu.

## Try it with sample data

`sample_data/sample_skyward_export.csv` is a synthetic five-employee export
(fake names, fake building codes, no real district data) that includes a
campus transfer and a role with no Eduphoria mapping, so you can see the
add/remove diff logic run without pointing the tool at anything real:

```bash
cp sample_data/sample_skyward_export.csv .
python skyward_to_eduphoria.py --date 2025-10-16
```

## Tests

```bash
pip install pytest
python -m pytest tests/
```

The test suite covers the pure data-transformation logic — date parsing,
active-assignment computation on a given date, and the add/remove row
generation for a campus transfer — run against the sample export in
`sample_data/`. It pre-seeds role mappings from the tool's own defaults so
tests never trigger the interactive "teach me this assignment" prompt or
touch `role_memory.json`. It does not attempt to test the interactive menu,
self-update, or desktop-shortcut code paths.

## About the CLI Engage importer

This repository previously also contained a Skyward-to-CLI-Engage importer.
That tool now lives in its own repository,
[cli-engage-roster-manager](https://github.com/Sykezzz/cli-engage-roster-manager),
since it targets a different downstream application and has its own release
cadence. It shared the effective-date diffing approach with this tool but
not its code.

## A note on data

This repository and its sample data contain no real student records,
employee records, or district-specific defaults. `KNOWN_APPLICATIONS` and
`DEFAULT_ROLE_MAPPINGS` reflect generic Eduphoria Management application and
role names, not any district's specific configuration — point it at your
own Skyward export and Eduphoria role list locally.

## License

MIT — see [LICENSE](LICENSE).
