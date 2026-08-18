"""
Unit tests for skyward_to_eduphoria.py.

These tests exercise the pure data-transformation logic (date parsing,
active-assignment computation, and daily add/remove row generation)
without touching the interactive menu, self-update, or shortcut-creation
code paths.

Role mappings used here ("Teacher", "Principal") are pre-populated from
DEFAULT_ROLE_MAPPINGS so that resolve_mapping() never falls through to the
interactive "teach_assignment" prompt during a test run.

Run with:  python -m pytest tests/
"""

import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import skyward_to_eduphoria as se  # noqa: E402


SAMPLE_CSV = Path(__file__).resolve().parent.parent / "sample_data" / "sample_skyward_export.csv"


@pytest.fixture
def mem():
    """An in-memory role-mapping store, seeded from the built-in defaults.

    Deliberately avoids se.load_memory()/save_memory() so tests never touch
    role_memory.json on disk.
    """
    return {
        "role_mappings": deepcopy(se.DEFAULT_ROLE_MAPPINGS),
        "seen_assignments": list(se.DEFAULT_ROLE_MAPPINGS.keys()),
    }


@pytest.fixture
def sample_df():
    df = pd.read_csv(SAMPLE_CSV, dtype=str)
    df.columns = df.columns.str.strip()
    return df


# ── parse_date / is_active_on ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("08/01/2025", date(2025, 8, 1)),
        ("2025-08-01", date(2025, 8, 1)),
        ("", None),
        ("nan", None),
        (None, None),
    ],
)
def test_parse_date(raw, expected):
    assert se.parse_date(raw) == expected


def test_is_active_on():
    start, end = date(2025, 8, 1), date(2025, 10, 15)
    assert se.is_active_on(start, end, date(2025, 9, 1)) is True
    assert se.is_active_on(start, end, date(2025, 10, 16)) is False
    assert se.is_active_on(start, None, date(2099, 1, 1)) is True


# ── active_assignments_on ──────────────────────────────────────────────────────

def test_active_assignments_on_filters_by_date():
    records = [
        {"assignment": "Teacher", "building": "ELM",
         "start": date(2025, 8, 1), "end": date(2025, 10, 15)},
        {"assignment": "Teacher", "building": "MSA",
         "start": date(2025, 10, 16), "end": None},
    ]
    before = se.active_assignments_on(records, date(2025, 9, 1))
    after = se.active_assignments_on(records, date(2025, 10, 20))
    assert before == {("Teacher", "ELM")}
    assert after == {("Teacher", "MSA")}


# ── find_column against the sample export ──────────────────────────────────────

def test_find_column_autodetects_known_headers(sample_df):
    col = se.find_column(
        sample_df,
        ["employee id", "employee number", "emp id", "emp no", "emp #", "staff id", "id"],
        "User Identifier",
    )
    assert col == "Employee ID"

    col = se.find_column(
        sample_df,
        ["building codes", "building code", "campus code", "location code",
         "school code", "building"],
        "Building Codes",
    )
    assert col == "Building Codes"


# ── build_rows_for_date: campus transfer and role addition ─────────────────────

def test_build_rows_for_date_detects_campus_transfer(sample_df, mem):
    rows, change_log = se.build_rows_for_date(
        sample_df,
        col_user="Employee ID",
        col_assign="Assignment Type Description",
        col_bldg="Building Codes",
        col_start="Start Date",
        col_end="End Date",
        col_name="Employee Name",
        mem=mem,
        target_date=date(2025, 10, 16),
    )

    actions = {(r["User Identifier"], r["Action"], r["Location"]) for r in rows}
    # James Wu (20002) should show a Remove from ELM and an Add at MSA,
    # both mapped through the "Teacher" role in DEFAULT_ROLE_MAPPINGS.
    assert ("20002", "Remove", "ELM") in actions
    assert ("20002", "Add", "MSA") in actions

    directions = {(c["emp_no"], c["direction"]) for c in change_log}
    assert ("20002", "LEAVING") in directions
    assert ("20002", "ENTERING") in directions


def test_build_rows_for_date_no_changes_on_steady_state(sample_df, mem):
    # Nothing changes between two ordinary days for employee 20001
    # (Maria Delgado, active Teacher at ELM the whole time).
    rows, change_log = se.build_rows_for_date(
        sample_df,
        col_user="Employee ID",
        col_assign="Assignment Type Description",
        col_bldg="Building Codes",
        col_start="Start Date",
        col_end="End Date",
        col_name="Employee Name",
        mem=mem,
        target_date=date(2025, 9, 15),
    )
    emp_ids_with_changes = {r["User Identifier"] for r in rows}
    assert "20001" not in emp_ids_with_changes
