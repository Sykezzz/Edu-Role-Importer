"""
skyward_to_eduphoria.py  —  Skyward → Eduphoria Role Importer
=============================================================
Run this script from the launcher on your Desktop, or directly:

    python skyward_to_eduphoria.py [OPTIONS]

OPTIONS (all optional):
    --catchup          Automatically scan for missed days without asking first
    --date YYYY-MM-DD  Treat a specific date as "today" (useful for testing)
    --update           Pull the latest script files and restart
    --help             Show this message
"""

# ── Standard library ──────────────────────────────────────────────────────────
import sys, os, json, csv, re, shutil, platform, subprocess, argparse, textwrap
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Third-party: auto-install pandas if missing ───────────────────────────────
def _ensure_pandas():
    try:
        import pandas as _pd
        return _pd
    except ImportError:
        pass
    print("\n  pandas is not installed — attempting automatic installation...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pandas", "--quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("  pandas installed successfully.\n")
    except Exception as e:
        print(f"\n[ERROR] Could not install pandas automatically: {e}")
        print("  Please run LAUNCH_WINDOWS.bat or LAUNCH_MAC_LINUX.sh instead.")
        sys.exit(1)
    try:
        import pandas as _pd
        return _pd
    except ImportError:
        print("\n[ERROR] pandas still not importable after installation.")
        print("  Close and reopen the terminal, then try the launcher again.")
        sys.exit(1)

pd = _ensure_pandas()


# ═══════════════════════════════════════════════════════════════════════════════
#  VERSION & UPDATE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = "2.1.0"

# Set UPDATE_BASE_URL to the raw-file base URL of your GitHub/shared drive repo
# so the auto-update feature can download new versions.
# Example: "https://raw.githubusercontent.com/yourorg/yourrepo/main"
# Leave as "" to disable network-based updating (manual file drop still works).
UPDATE_BASE_URL = ""
UPDATE_FILES    = [
    "skyward_to_eduphoria.py",
    "LAUNCH_WINDOWS.bat",
    "LAUNCH_MAC_LINUX.sh",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  PATHS & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR  = SCRIPT_PATH.parent
MEMORY_FILE = SCRIPT_DIR / "role_memory.json"
LOG_FILE    = SCRIPT_DIR / "run_log.json"
OUTPUT_DIR  = SCRIPT_DIR

KNOWN_APPLICATIONS = [
    "Strive Evaluation",
    "Formspace",
    "Forethought",
    "Aware",
    "Strive Professional Learning",
]

DEFAULT_ROLE_MAPPINGS = {
    "Principal": [
        {"role": "Campus Administrator", "application": "Strive Evaluation"},
        {"role": "Campus Administrator", "application": "Strive Professional Learning"},
    ],
    "Assistant Principal": [
        {"role": "Campus Administrator", "application": "Strive Evaluation"},
        {"role": "Campus Administrator", "application": "Strive Professional Learning"},
    ],
    "Teacher": [
        {"role": "Teacher", "application": "Strive Evaluation"},
        {"role": "Teacher", "application": "Strive Professional Learning"},
    ],
    "Instructional Coach": [
        {"role": "Instructional Coach", "application": "Strive Evaluation"},
        {"role": "Instructional Coach", "application": "Formspace"},
    ],
    "Counselor": [
        {"role": "Counselor", "application": "Strive Evaluation"},
    ],
    "Campus Support Staff": [
        {"role": "Non-Classroom Professional", "application": "Strive Evaluation"},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  COLOUR / FORMATTING
# ═══════════════════════════════════════════════════════════════════════════════

USE_COLOUR = sys.stdout.isatty() and (
    platform.system() != "Windows"
    or os.environ.get("ANSICON")
    or os.environ.get("WT_SESSION")
)

def _c(code, text): return f"\033[{code}m{text}\033[0m" if USE_COLOUR else text
def bold(t):   return _c("1",  t)
def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def red(t):    return _c("31", t)
def cyan(t):   return _c("36", t)
def dim(t):    return _c("2",  t)

def hr(char="─", width=66): print(dim(char * width))

def banner(title, char="═"):
    w = 66
    print(); print(bold(char * w)); print(bold(f"  {title}")); print(bold(char * w))

def info(msg):    print(f"  {cyan('i')}  {msg}")
def success(msg): print(f"  {green('+')}  {msg}")
def warn(msg):    print(f"  {yellow('!')}  {msg}")
def err(msg):     print(f"  {red('x')}  {msg}")

def section(title):
    print(); hr(); print(f"  {bold(title)}"); hr()


# ═══════════════════════════════════════════════════════════════════════════════
#  INPUT HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def ask(question, default=""):
    suffix = dim(f" [{default}]") if default else ""
    try:
        ans = input(f"\n  {question}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print(); sys.exit(0)
    return ans if ans else default

def ask_yn(question, default=True):
    hint = dim("(Y/n)") if default else dim("(y/N)")
    try:
        ans = input(f"\n  {question} {hint}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(); sys.exit(0)
    if ans in ("y", "yes"): return True
    if ans in ("n", "no"):  return False
    return default

def pick_from_list(options, label="option", allow_custom=True, allow_skip=False):
    print()
    for i, opt in enumerate(options, 1):
        print(f"    {dim(str(i)+'.')} {opt}")
    extras = []
    if allow_custom:
        extras.append(f"{dim(str(len(options)+1)+'.')} Enter a custom value")
    if allow_skip:
        extras.append(f"{dim(str(len(options)+len(extras)+1)+'.')} Skip / leave blank")
    for e in extras:
        print(f"    {e}")
    top = len(options) + len(extras)
    while True:
        try:
            raw = input(f"\n  Your choice (1-{top}): ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); sys.exit(0)
        if not raw.isdigit():
            warn("Please enter a number."); continue
        n = int(raw)
        if 1 <= n <= len(options): return options[n - 1]
        if allow_custom and n == len(options) + 1:
            custom = ask("Custom value").strip()
            return custom if custom else None
        if allow_skip and n == top: return None
        warn(f"Please enter a number between 1 and {top}.")


# ═══════════════════════════════════════════════════════════════════════════════
#  MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            mem = json.load(f)
    else:
        mem = {}
    mem.setdefault("role_mappings", {})
    mem.setdefault("seen_assignments", [])
    for k, v in DEFAULT_ROLE_MAPPINGS.items():
        if k.lower() not in {ek.lower() for ek in mem["role_mappings"]}:
            mem["role_mappings"][k] = v
            if k not in mem["seen_assignments"]:
                mem["seen_assignments"].append(k)
    return mem

def save_memory(mem):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2)

def get_mapping_ci(mem, assignment):
    lower = assignment.lower()
    for k, v in mem["role_mappings"].items():
        if k.lower() == lower: return v
    return None

def set_mapping_ci(mem, assignment, value):
    lower = assignment.lower()
    for k in list(mem["role_mappings"].keys()):
        if k.lower() == lower:
            del mem["role_mappings"][k]
            if k in mem["seen_assignments"]:
                mem["seen_assignments"].remove(k)
    mem["role_mappings"][assignment] = value
    if assignment not in mem["seen_assignments"]:
        mem["seen_assignments"].append(assignment)


# ═══════════════════════════════════════════════════════════════════════════════
#  RUN LOG
# ═══════════════════════════════════════════════════════════════════════════════

def load_log():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_dates": [], "last_run": None}

def save_log(log):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)

def record_run(log, run_date, had_changes):
    ds = run_date.isoformat()
    log["processed_dates"] = [e for e in log["processed_dates"] if e["date"] != ds]
    log["processed_dates"].append({"date": ds, "had_changes": had_changes})
    log["last_run"] = ds
    save_log(log)

def missed_dates(log, today):
    if not log.get("last_run"): return []
    last      = date.fromisoformat(log["last_run"])
    processed = {e["date"] for e in log.get("processed_dates", [])}
    missed, d = [], last + timedelta(days=1)
    while d < today:
        if d.isoformat() not in processed:
            missed.append(d)
        d += timedelta(days=1)
    return missed


# ═══════════════════════════════════════════════════════════════════════════════
#  DATE UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def parse_date(value):
    if value is None: return None
    s = str(value).strip()
    if s in ("", "nan", "NaT", "None", "NaN"): return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y",
                "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try: return datetime.strptime(s, fmt).date()
        except ValueError: pass
    try: return pd.to_datetime(s).date()
    except Exception: return None

def is_active_on(start, end, target):
    if start is None or target < start: return False
    if end is not None and target > end: return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  COLUMN DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def find_column(df, candidates, label, required=True):
    lower_map = {c.lower().strip(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    if not required: return None
    warn(f"Could not auto-detect the '{label}' column.")
    print("  Available columns:")
    for i, col in enumerate(df.columns, 1):
        print(f"    {dim(str(i)+'.')} {col}")
    while True:
        raw = ask(f"Which column is '{label}'? Enter the number")
        if raw.isdigit() and 1 <= int(raw) <= len(df.columns):
            return df.columns[int(raw) - 1]
        warn("Please enter a valid number.")


# ═══════════════════════════════════════════════════════════════════════════════
#  ROLE TEACHING
# ═══════════════════════════════════════════════════════════════════════════════

def teach_assignment(assignment, mem):
    section(f'NEW ASSIGNMENT TYPE: "{assignment}"')
    print(
        "  This assignment is needed for today's import but hasn't been configured.\n"
        "  Please answer the questions below. Your answers are saved permanently."
    )
    if not ask_yn(
        '  Does this assignment need an Eduphoria role?\n'
        '  (Choose NO for substitutes, volunteers, aides, etc.)', default=True
    ):
        info("Marked as needing no Eduphoria role.")
        set_mapping_ci(mem, assignment, "NO_ROLE")
        save_memory(mem)
        return "NO_ROLE"

    if ask_yn("  Is this a brand-new role not yet in Eduphoria Management?", default=False):
        warn("Create this role in Eduphoria Management BEFORE running the import.")

    mappings = []
    print("\n  An assignment can map to multiple role+application pairs.")
    print("  Leave the Role Name blank when you are finished.\n")
    while True:
        print(f"  {dim('--- Mapping #'+str(len(mappings)+1)+' ---')}")
        role = ask("  Eduphoria Role Name  (blank = done)").strip()
        if not role:
            if mappings: break
            warn("Enter at least one role."); continue
        print(f"\n  Which application does '{role}' belong to?")
        app = pick_from_list(KNOWN_APPLICATIONS, label="application", allow_custom=True)
        if not app:
            warn("Application cannot be blank."); continue
        mappings.append({"role": role, "application": app})
        success(f"Added: {bold(role)}  ->  {app}")
        if not ask_yn("  Add another role/application for this assignment?", default=False):
            break

    set_mapping_ci(mem, assignment, mappings)
    save_memory(mem)
    return mappings

def resolve_mapping(assignment, mem):
    val = get_mapping_ci(mem, assignment)
    if val is None:
        return teach_assignment(assignment, mem)
    return val


# ═══════════════════════════════════════════════════════════════════════════════
#  FUZZY SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

def fuzzy_match(needle, haystack, threshold=0.4):
    needle_lower  = needle.lower()
    needle_tokens = set(re.split(r'\W+', needle_lower))
    results = []
    for item in haystack:
        item_lower = item.lower()
        if needle_lower in item_lower:
            results.append(item); continue
        item_tokens = set(re.split(r'\W+', item_lower))
        if not needle_tokens or not item_tokens: continue
        overlap = needle_tokens & item_tokens
        if len(overlap) / len(needle_tokens | item_tokens) >= threshold:
            results.append(item)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  CORE PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def active_assignments_on(records, target):
    return {
        (r["assignment"], r["building"])
        for r in records
        if is_active_on(r["start"], r["end"], target)
        and r["assignment"]
        and r["assignment"].lower() not in ("", "nan")
    }


def build_rows_for_date(df, col_user, col_assign, col_bldg,
                        col_start, col_end, col_name, mem, target_date):
    """
    Returns:
        output_rows — list of dicts ready to write to the Eduphoria import CSV
        change_log  — list of human-readable change entries for the summary table
    """
    yesterday   = target_date - timedelta(days=1)
    output_rows = []
    change_log  = []

    for user_id, group in df.groupby(col_user):
        user_id = str(user_id).strip()
        if not user_id or user_id.lower() == "nan":
            continue

        # Optional display name
        display_name = ""
        if col_name:
            names = group[col_name].dropna().astype(str).str.strip()
            names = names[names.str.lower() != "nan"]
            if not names.empty:
                display_name = names.iloc[0]

        records = []
        for _, row in group.iterrows():
            a = str(row.get(col_assign, "")).strip()
            b = str(row.get(col_bldg,   "")).strip()
            records.append({
                "assignment": a if a.lower() != "nan" else "",
                "building":   b if b.lower() != "nan" else "",
                "start":      parse_date(row[col_start]),
                "end":        parse_date(row[col_end]),
            })

        today_set     = active_assignments_on(records, target_date)
        yesterday_set = active_assignments_on(records, yesterday)
        removed       = yesterday_set - today_set
        added         = today_set     - yesterday_set

        if not removed and not added:
            continue

        # ── REMOVE rows ───────────────────────────────────────────────────────
        for (assignment, building) in sorted(removed):
            mapping  = resolve_mapping(assignment, mem)
            location = building if building else "District"
            if mapping == "NO_ROLE" or not mapping:
                change_log.append({
                    "emp_no":    user_id,
                    "name":      display_name,
                    "date":      target_date.isoformat(),
                    "direction": "LEAVING",
                    "position":  assignment,
                    "building":  location,
                    "note":      "(no Eduphoria role)",
                })
                continue
            for m in mapping:
                output_rows.append({
                    "User Identifier":  user_id,
                    "Role Name":        m["role"],
                    "Application Name": m["application"],
                    "Location":         location,
                    "Action":           "Remove",
                    "_date":            target_date.isoformat(),
                })
            change_log.append({
                "emp_no":    user_id,
                "name":      display_name,
                "date":      target_date.isoformat(),
                "direction": "LEAVING",
                "position":  assignment,
                "building":  location,
                "note":      f"{len(mapping)} role(s) removed",
            })

        # ── ADD rows ──────────────────────────────────────────────────────────
        for (assignment, building) in sorted(added):
            mapping  = resolve_mapping(assignment, mem)
            location = building if building else "District"
            if mapping == "NO_ROLE" or not mapping:
                change_log.append({
                    "emp_no":    user_id,
                    "name":      display_name,
                    "date":      target_date.isoformat(),
                    "direction": "ENTERING",
                    "position":  assignment,
                    "building":  location,
                    "note":      "(no Eduphoria role)",
                })
                continue
            for m in mapping:
                output_rows.append({
                    "User Identifier":  user_id,
                    "Role Name":        m["role"],
                    "Application Name": m["application"],
                    "Location":         location,
                    "Action":           "Add",
                    "_date":            target_date.isoformat(),
                })
            change_log.append({
                "emp_no":    user_id,
                "name":      display_name,
                "date":      target_date.isoformat(),
                "direction": "ENTERING",
                "position":  assignment,
                "building":  location,
                "note":      f"{len(mapping)} role(s) added",
            })

    return output_rows, change_log


def _trunc(s, w):
    """Truncate string to width w, adding ellipsis if needed."""
    return (s[:w-1] + "~") if len(s) > w else s.ljust(w)


def print_change_summary(change_log, dates_processed):
    """Print a formatted two-section table of all role changes."""
    if not change_log:
        return

    section("EMPLOYEE ROLE CHANGE SUMMARY")

    leavers  = [c for c in change_log if c["direction"] == "LEAVING"]
    entering = [c for c in change_log if c["direction"] == "ENTERING"]
    multi    = len(dates_processed) > 1

    # Dynamic column widths (capped so the table stays readable)
    all_entries = change_log
    W_EMP  = min(14, max(6,  max(len(c["emp_no"])   for c in all_entries)))
    W_NAME = min(22, max(12, max(len(c["name"])      for c in all_entries)))
    W_POS  = min(32, max(20, max(len(c["position"])  for c in all_entries)))
    W_LOC  = min(12, max(8,  max(len(c["building"])  for c in all_entries)))
    W_NOTE = 24

    def row(emp, name, pos, loc, note):
        return (
            f"  {_trunc(emp,  W_EMP )}  "
            f"{_trunc(name, W_NAME)}  "
            f"{_trunc(pos,  W_POS )}  "
            f"{_trunc(loc,  W_LOC )}  "
            f"{note}"
        )

    def header():
        print(row(bold("Emp #"), bold("Name"), bold("Position"),
                  bold("Location"), bold("Eduphoria action")))
        hr("─", W_EMP + W_NAME + W_POS + W_LOC + W_NOTE + 12)

    # ── Leaving section ───────────────────────────────────────────────────────
    if leavers:
        print(f"\n  {red('v  LEAVING / ROLE BEING REMOVED')}  "
              f"{dim('('+str(len(leavers))+' employee(s))')}\n")
        header()
        for c in sorted(leavers, key=lambda x: (x["date"], x["emp_no"])):
            date_tag = f"[{c['date']}] " if multi else ""
            print(row(c["emp_no"], c["name"], c["position"],
                      c["building"], dim(date_tag) + c["note"]))

    # ── Entering section ──────────────────────────────────────────────────────
    if entering:
        print(f"\n  {green('^  ENTERING / ROLE BEING ADDED')}  "
              f"{dim('('+str(len(entering))+' employee(s))')}\n")
        header()
        for c in sorted(entering, key=lambda x: (x["date"], x["emp_no"])):
            date_tag = f"[{c['date']}] " if multi else ""
            print(row(c["emp_no"], c["name"], c["position"],
                      c["building"], dim(date_tag) + c["note"]))

    print()
    info(f"Total changes: {len(leavers)} leaving, {len(entering)} entering")
    print()


def write_csv(rows, path):
    fieldnames = ["User Identifier", "Role Name", "Application Name", "Location", "Action"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ═══════════════════════════════════════════════════════════════════════════════
#  FILE LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_skyward_file():
    csv_files = sorted(
        list(SCRIPT_DIR.glob("*.csv"))
        + list(SCRIPT_DIR.glob("*.xlsx"))
        + list(SCRIPT_DIR.glob("*.xls"))
    )
    csv_files = [f for f in csv_files if not f.name.startswith("eduphoria_import")]
    if not csv_files:
        err("No CSV or Excel files found in the script folder.")
        print("  Place your Skyward export here, then try again.")
        return (None,) * 7

    print()
    for i, f in enumerate(csv_files, 1):
        print(f"    {dim(str(i)+'.')} {f.name}")

    if len(csv_files) == 1:
        chosen = csv_files[0]
        info(f"Using: {chosen.name}")
    else:
        while True:
            raw = ask("Which file is your Skyward report? Enter the number")
            if raw.isdigit() and 1 <= int(raw) <= len(csv_files):
                chosen = csv_files[int(raw) - 1]; break
            warn("Please enter a valid number.")

    info(f"Loading {chosen.name} ...")
    try:
        if chosen.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(chosen, dtype=str)
        else:
            for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
                try:
                    df = pd.read_csv(chosen, dtype=str, encoding=enc); break
                except UnicodeDecodeError:
                    continue
    except Exception as e:
        err(f"Could not open the file: {e}")
        return (None,) * 7

    df.columns = df.columns.str.strip()
    success(f"Loaded {len(df):,} rows, {len(df.columns)} columns.")

    col_user   = find_column(df,
        ["email", "email address", "employee email", "user email",
         "external id", "employee id", "employee number", "emp id",
         "emp no", "emp #", "staff id", "id"],
        "User Identifier (employee number or email)")
    col_assign = find_column(df,
        ["assignment type description", "assignment type desc",
         "assignment description", "assignment type",
         "job description", "position description"],
        "Assignment Type Description")
    col_bldg   = find_column(df,
        ["building codes", "building code", "campus code",
         "location code", "school code", "building"],
        "Building Codes")
    col_start  = find_column(df,
        ["start date", "startdate", "begin date", "effective date"],
        "Start Date")
    col_end    = find_column(df,
        ["end date", "enddate", "termination date", "end"],
        "End Date")
    col_name   = find_column(df,
        ["employee name", "full name", "name", "last, first",
         "last name", "display name", "preferred name"],
        "Employee Name", required=False)

    print()
    info(f"User Identifier  ->  '{bold(col_user)}'")
    info(f"Assignment       ->  '{bold(col_assign)}'")
    info(f"Building Codes   ->  '{bold(col_bldg)}'")
    info(f"Start Date       ->  '{bold(col_start)}'")
    info(f"End Date         ->  '{bold(col_end)}'")
    if col_name:
        info(f"Employee Name    ->  '{bold(col_name)}'  {dim('(used for summary display)')}")
    else:
        info(f"Employee Name    ->  {dim('not found — summary will show Emp # only')}")

    if not ask_yn("\n  Do these column mappings look correct?", default=True):
        warn("Re-run and select the correct columns when prompted.")
        sys.exit(0)

    return df, col_user, col_assign, col_bldg, col_start, col_end, col_name


# ═══════════════════════════════════════════════════════════════════════════════
#  GENERATE IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

def generate_import(mem, log, today, catchup=False):
    section("GENERATE EDUPHORIA IMPORT FILE")

    missed = missed_dates(log, today)
    dates_to_process = [today]

    if missed:
        warn(f"Missed dates detected: {', '.join(d.isoformat() for d in missed)}")
        if catchup or ask_yn(
            f"  Scan those {len(missed)} missed day(s) for changes too?", default=True
        ):
            dates_to_process = sorted(missed) + [today]
            info(f"Will process {len(dates_to_process)} date(s).")
        else:
            info("Only processing today.")

    result = load_skyward_file()
    if result[0] is None:
        return
    df, col_user, col_assign, col_bldg, col_start, col_end, col_name = result

    all_rows    = []
    all_changes = []

    for proc_date in dates_to_process:
        info(f"Processing {proc_date} ...")
        rows, changes = build_rows_for_date(
            df, col_user, col_assign, col_bldg, col_start, col_end,
            col_name, mem, proc_date,
        )
        all_rows.extend(rows)
        all_changes.extend(changes)
        record_run(log, proc_date, bool(rows))
        if rows:
            success(f"  {proc_date}: {len(rows)} CSV row(s) generated.")
        else:
            info(f"  {proc_date}: No role-mapped changes detected.")

    # Always show the summary — even entries with no Eduphoria role are listed
    if all_changes:
        print_change_summary(all_changes, dates_to_process)
    else:
        print()
        info("No assignment changes found for any of the processed date(s).")
        info("No output file was created — nothing to import into Eduphoria.")
        print()
        ask("Press Enter to return to the main menu")
        return

    if not all_rows:
        info("All detected changes involve assignments with no Eduphoria role.")
        info("No CSV file was created.")
        print()
        ask("Press Enter to return to the main menu")
        return

    label = today.isoformat()
    if len(dates_to_process) > 1:
        label = (f"{dates_to_process[0].isoformat()}"
                 f"_to_{dates_to_process[-1].isoformat()}")
    out_path = OUTPUT_DIR / f"eduphoria_import_{label}.csv"
    write_csv(all_rows, out_path)

    removes = sum(1 for r in all_rows if r["Action"] == "Remove")
    adds    = sum(1 for r in all_rows if r["Action"] == "Add")

    banner("DONE")
    success(f"Output file : {out_path.name}")
    info(   f"Total rows  : {len(all_rows)}  ({removes} Remove  |  {adds} Add)")
    print()
    print("  NEXT STEPS:")
    print("    1. Review the summary above and spot-check the CSV.")
    print("    2. Log in to Eduphoria -> Management -> Import Roles.")
    print("    3. Upload the file, review the preview, then confirm.")
    print()
    ask("Press Enter to return to the main menu")


# ═══════════════════════════════════════════════════════════════════════════════
#  MANAGE MAPPINGS
# ═══════════════════════════════════════════════════════════════════════════════

def manage_mappings_menu(mem):
    while True:
        section("MANAGE ROLE MAPPINGS")
        options = [
            "View all current mappings",
            "Edit a specific mapping",
            "Delete / reset a mapping",
            "Mass-update with fuzzy search",
            "Mark an assignment as needing NO role",
            "Back to main menu",
        ]
        for i, o in enumerate(options, 1):
            print(f"    {dim(str(i)+'.')} {o}")
        choice = ask("Choose an option")
        if not choice.isdigit() or not (1 <= int(choice) <= len(options)):
            warn("Please enter a valid number."); continue
        c = int(choice)
        if c == 1: _view_all_mappings(mem)
        elif c == 2: _edit_mapping(mem)
        elif c == 3: _delete_mapping(mem)
        elif c == 4: _mass_update(mem)
        elif c == 5: _mark_no_role(mem)
        elif c == 6: break


def _view_all_mappings(mem):
    section("ALL CURRENT MAPPINGS")
    if not mem["role_mappings"]:
        info("No mappings saved yet."); return
    for assignment, val in sorted(mem["role_mappings"].items()):
        print(f"\n  {bold(assignment)}")
        if val == "NO_ROLE":
            print(f"    -> {yellow('No Eduphoria role required')}")
        else:
            for m in val:
                print(f"    -> {m['role']}  [{m['application']}]")
    print()
    ask("Press Enter to continue")


def _edit_mapping(mem):
    section("EDIT A MAPPING")
    assignments = sorted(mem["role_mappings"].keys())
    if not assignments:
        warn("No mappings to edit."); return
    print("  Select the assignment to edit:")
    chosen = pick_from_list(assignments, allow_custom=False, allow_skip=True)
    if not chosen: return
    del mem["role_mappings"][chosen]
    if chosen in mem["seen_assignments"]:
        mem["seen_assignments"].remove(chosen)
    save_memory(mem)
    teach_assignment(chosen, mem)


def _delete_mapping(mem):
    section("DELETE A MAPPING")
    assignments = sorted(mem["role_mappings"].keys())
    if not assignments:
        warn("No mappings to delete."); return
    print("  Select the assignment to delete:")
    chosen = pick_from_list(assignments, allow_custom=False, allow_skip=True)
    if not chosen: return
    if ask_yn(f'  Delete mapping for "{chosen}"? This cannot be undone.', default=False):
        del mem["role_mappings"][chosen]
        if chosen in mem["seen_assignments"]:
            mem["seen_assignments"].remove(chosen)
        save_memory(mem)
        success(f'Mapping for "{chosen}" deleted.')


def _mass_update(mem):
    section("MASS UPDATE -- FUZZY SEARCH")
    print(
        "  Type a word or phrase to find matching assignment descriptions.\n"
        "  You can then apply a new mapping to all of them at once.\n"
    )
    needle = ask("  Search phrase (e.g. 'Academic Trainer')").strip()
    if not needle: return

    matches = fuzzy_match(needle, sorted(mem["role_mappings"].keys()))
    if not matches:
        warn(f'No assignments found matching "{needle}".'); return

    print(f"\n  Found {len(matches)} matching assignment(s):")
    for m in matches:
        val = mem["role_mappings"].get(m)
        if val == "NO_ROLE":
            tag = yellow("NO_ROLE")
        elif val:
            tag = ", ".join(f"{x['role']} [{x['application']}]" for x in val)
        else:
            tag = dim("(unknown)")
        print(f"    * {bold(m)}  ->  {tag}")

    if not ask_yn(f"\n  Apply a new mapping to ALL {len(matches)} of these?", default=False):
        return

    if not ask_yn("  Do these assignments need an Eduphoria role?", default=True):
        new_mapping = "NO_ROLE"
    else:
        new_mapping = []
        print("\n  Enter the role+application pairs (blank role name to finish):")
        while True:
            role = ask("  Eduphoria Role Name (blank to finish)").strip()
            if not role:
                if new_mapping: break
                warn("Enter at least one role."); continue
            print(f"\n  Application for '{role}':")
            app = pick_from_list(KNOWN_APPLICATIONS, allow_custom=True)
            if not app:
                warn("Application cannot be blank."); continue
            new_mapping.append({"role": role, "application": app})
            success(f"Added: {role}  ->  {app}")
            if not ask_yn("  Add another?", default=False): break

    for m in matches:
        set_mapping_ci(mem, m, new_mapping)
    save_memory(mem)
    success(f"Updated {len(matches)} mapping(s).")


def _mark_no_role(mem):
    section("MARK ASSIGNMENT AS NEEDING NO ROLE")
    assignment = ask("  Assignment Type Description (exact or approximate)").strip()
    if not assignment: return
    matches = fuzzy_match(assignment, list(mem["role_mappings"].keys()))
    if matches:
        print("\n  Found similar existing mapping(s):")
        for m in matches: print(f"    * {m}")
        chosen = pick_from_list(
            matches + [f'Create new entry: "{assignment}"'],
            allow_custom=False, allow_skip=True
        )
        if chosen and chosen.startswith("Create new entry"): chosen = assignment
    else:
        chosen = assignment
    if not chosen: return
    if ask_yn(f'  Mark "{chosen}" as needing NO Eduphoria role?', default=True):
        set_mapping_ci(mem, chosen, "NO_ROLE")
        save_memory(mem)
        success(f'"{chosen}" marked as NO_ROLE.')


# ═══════════════════════════════════════════════════════════════════════════════
#  SELF-UPDATE
# ═══════════════════════════════════════════════════════════════════════════════

def self_update():
    section("CHECK FOR / APPLY UPDATES")

    if not UPDATE_BASE_URL:
        warn("Auto-update from the internet is not configured.")
        print(
            "\n  To enable it, your administrator needs to set UPDATE_BASE_URL\n"
            "  at the top of the script to point to wherever new versions are hosted.\n"
            "\n  You can still apply updates manually:\n"
            "    1. Receive the new script files from your administrator.\n"
            "    2. Choose the manual update option below.\n"
            "    3. Your role_memory.json and run_log.json are NEVER overwritten,\n"
            "       so all your settings and history are always preserved.\n"
        )
        _offer_manual_update()
        return

    # ── Network update ────────────────────────────────────────────────────────
    import urllib.request
    info("Checking for updates ...")
    tmp_dir = SCRIPT_DIR / "_update_tmp"
    tmp_dir.mkdir(exist_ok=True)
    downloaded = []

    try:
        for fname in UPDATE_FILES:
            url  = f"{UPDATE_BASE_URL.rstrip('/')}/{fname}"
            dest = tmp_dir / fname
            try:
                urllib.request.urlretrieve(url, dest)
                downloaded.append(fname)
                success(f"Downloaded: {fname}")
            except Exception as e:
                warn(f"Could not download {fname}: {e}")

        if not downloaded:
            err("No files could be downloaded. Check your internet connection.")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return

        remote_py      = tmp_dir / "skyward_to_eduphoria.py"
        remote_version = VERSION
        if remote_py.exists():
            for line in remote_py.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("VERSION"):
                    try:
                        remote_version = line.split('"')[1] if '"' in line else line.split("'")[1]
                    except IndexError:
                        pass
                    break

        if remote_version == VERSION:
            info(f"You already have the latest version ({VERSION}).")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            ask("Press Enter to return to the main menu")
            return

        print(f"\n  Update available:  {dim(VERSION)} -> {green(remote_version)}")
        if not ask_yn("  Install the update now?", default=True):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return

        _apply_update(tmp_dir, downloaded, remote_version)

    except Exception as e:
        err(f"Update failed: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _offer_manual_update():
    """Ask user to point to a folder of new files and apply them."""
    if not ask_yn(
        "  Do you have a folder of updated script files to apply now?",
        default=False
    ):
        ask("Press Enter to return to the main menu")
        return

    raw_path = ask("  Path to the folder containing the new files").strip().strip('"\'')
    src_dir  = Path(raw_path)
    if not src_dir.is_dir():
        err(f"Folder not found: {src_dir}"); return

    found = [f for f in UPDATE_FILES if (src_dir / f).exists()]
    if not found:
        err("No recognised script files found in that folder."); return

    print(f"\n  Found {len(found)} file(s) to install: {', '.join(found)}")
    if not ask_yn(
        "  Apply the update? (Your settings and run history are preserved.)",
        default=True
    ):
        return

    _apply_update(src_dir, found, remote_version="(manual)")


def _apply_update(src_dir, filenames, remote_version):
    """
    Replace script files in both the running folder and the Desktop copy.
    Never touches role_memory.json or run_log.json.
    """
    protected = {MEMORY_FILE.name, LOG_FILE.name}
    locations = [SCRIPT_DIR]

    desktop_folder = Path.home() / "Desktop" / "Skyward_Eduphoria"
    if desktop_folder.exists() and desktop_folder != SCRIPT_DIR:
        locations.append(desktop_folder)

    for dest_dir in locations:
        label = "Desktop copy" if dest_dir == desktop_folder else "main folder"
        for fname in filenames:
            if fname in protected:
                continue
            src  = src_dir  / fname
            dest = dest_dir / fname
            if src.exists():
                shutil.copy2(src, dest)
                # Make shell scripts executable
                if dest.suffix == ".sh":
                    dest.chmod(0o755)
                success(f"Updated {label}: {fname}")

    # Rebuild the Desktop shortcut so it still points at the right launcher
    if desktop_folder.exists():
        system = platform.system()
        bat = desktop_folder / "LAUNCH_WINDOWS.bat"
        sh  = desktop_folder / "LAUNCH_MAC_LINUX.sh"
        try:
            if system == "Windows" and bat.exists():
                _make_windows_shortcut(bat, desktop_folder)
            elif system == "Darwin" and sh.exists():
                _make_mac_shortcut(sh, desktop_folder)
            elif system == "Linux" and sh.exists():
                _make_linux_shortcut(sh, desktop_folder)
            info("Desktop shortcut refreshed.")
        except Exception as e:
            warn(f"Could not refresh Desktop shortcut: {e}")

    # Cleanup temp dir
    try:
        if src_dir.name == "_update_tmp":
            shutil.rmtree(src_dir, ignore_errors=True)
    except Exception:
        pass

    banner("UPDATE COMPLETE")
    success(f"All files updated to version {remote_version}.")
    info("Your settings, mappings, and run history are unchanged.")
    info("Close and reopen the launcher to start using the new version.")
    ask("\nPress Enter to exit (then reopen the launcher)")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
#  DESKTOP SHORTCUT
# ═══════════════════════════════════════════════════════════════════════════════

def add_to_desktop():
    system  = platform.system()
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    target_dir = desktop / "Skyward_Eduphoria"
    target_dir.mkdir(exist_ok=True)

    files_to_copy = [SCRIPT_PATH]
    for lf in (SCRIPT_DIR / "LAUNCH_WINDOWS.bat", SCRIPT_DIR / "LAUNCH_MAC_LINUX.sh"):
        if lf.exists():
            files_to_copy.append(lf)
    for sf in (MEMORY_FILE, LOG_FILE):
        if sf.exists():
            files_to_copy.append(sf)

    for src in files_to_copy:
        shutil.copy2(src, target_dir / src.name)
    success(f"Files copied to: {target_dir}")

    bat = target_dir / "LAUNCH_WINDOWS.bat"
    sh  = target_dir / "LAUNCH_MAC_LINUX.sh"
    py  = target_dir / SCRIPT_PATH.name

    if system == "Windows":
        _make_windows_shortcut(bat if bat.exists() else py, target_dir)
    elif system == "Darwin":
        if sh.exists(): sh.chmod(0o755)
        _make_mac_shortcut(sh if sh.exists() else py, target_dir)
    elif system == "Linux":
        if sh.exists(): sh.chmod(0o755)
        _make_linux_shortcut(sh if sh.exists() else py, target_dir)
    else:
        warn(f"Unsupported OS ({system}) — files copied but no shortcut created.")

    print()
    info("Use the Desktop shortcut to start the importer from now on.")
    info("The launcher handles Python and pandas checks automatically.")


def _make_windows_shortcut(target, folder):
    shortcut_path = folder.parent / "Skyward Eduphoria.lnk"
    ps = textwrap.dedent(f"""\
        $ws = New-Object -ComObject WScript.Shell
        $s  = $ws.CreateShortcut('{shortcut_path}')
        $s.TargetPath       = 'cmd.exe'
        $s.Arguments        = '/k "{target}"'
        $s.WorkingDirectory = '{folder}'
        $s.Description      = 'Skyward to Eduphoria Importer'
        $s.WindowStyle      = 1
        $s.Save()
    """)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            success(f"Desktop shortcut created: {shortcut_path.name}")
        else:
            raise RuntimeError(result.stderr.strip())
    except Exception as e:
        warn(f"Could not create shortcut automatically: {e}")
        info("Right-click LAUNCH_WINDOWS.bat -> Send To -> Desktop (create shortcut).")


def _make_mac_shortcut(launcher, folder):
    app_dir  = folder.parent / "Skyward Eduphoria.app"
    contents = app_dir / "Contents" / "MacOS"
    contents.mkdir(parents=True, exist_ok=True)
    run_sh   = contents / "run.sh"
    run_sh.write_text(f'#!/bin/bash\nexec "{launcher}"\n')
    run_sh.chmod(0o755)
    (app_dir / "Contents" / "Info.plist").write_text(textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0"><dict>
          <key>CFBundleName</key><string>Skyward Eduphoria</string>
          <key>CFBundleExecutable</key><string>run.sh</string>
          <key>CFBundleIdentifier</key><string>com.district.skyward-eduphoria</string>
          <key>CFBundleVersion</key><string>1.0</string>
        </dict></plist>
    """))
    success(f"Mac app bundle created: {app_dir.name}")
    info("Double-click 'Skyward Eduphoria' on your Desktop to launch.")
    info("If macOS blocks it: right-click the app -> Open -> Open.")


def _make_linux_shortcut(launcher, folder):
    entry = folder.parent / "skyward_eduphoria.desktop"
    entry.write_text(textwrap.dedent(f"""\
        [Desktop Entry]
        Name=Skyward Eduphoria Importer
        Exec=bash "{launcher}"
        Path={folder}
        Type=Application
        Terminal=true
        Comment=Convert Skyward exports to Eduphoria role import CSV
        Categories=Office;
    """))
    entry.chmod(0o755)
    try:
        subprocess.run(["gio", "set", str(entry), "metadata::trusted", "true"],
                       capture_output=True)
    except Exception:
        pass
    success(f"Desktop launcher created: {entry.name}")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════

MENU_ITEMS = [
    ("Generate import file",
     "Reads your Skyward export, displays who is entering/leaving each role,\n"
     "     and creates the Eduphoria role import CSV. Catches up missed days."),
    ("Manage role mappings",
     "View, edit, delete, or mass-update assignment -> role mappings.\n"
     "     Also lets you mark assignments that need no Eduphoria role."),
    ("Add shortcut to Desktop",
     "Copies the script to your Desktop and creates a double-click launcher.\n"
     "     Python and pandas are installed automatically if needed."),
    ("View run history",
     "Shows the last 30 dates the script ran and whether any changes\n"
     "     were found each time."),
    ("Check for / apply updates",
     "Installs the latest version of the script files. Downloads from the\n"
     "     configured URL, or lets you point to a folder of new files manually.\n"
     "     Your settings, mappings, and run history are always preserved."),
    ("Exit", "Quit the script."),
]

def print_menu():
    banner(f"SKYWARD -> EDUPHORIA  |  MAIN MENU  {dim('v'+VERSION)}")
    print("  What would you like to do?\n")
    for i, (title, desc) in enumerate(MENU_ITEMS, 1):
        print(f"  {bold(str(i)+'.')} {bold(title)}")
        print(f"     {dim(desc)}")
        print()
    hr()

def view_run_history(log):
    section("RUN HISTORY")
    entries = sorted(log.get("processed_dates", []), key=lambda e: e["date"])
    if not entries:
        info("No runs recorded yet.")
    else:
        print(f"  {'Date':<14} {'Changes found?'}")
        hr("─", 40)
        for e in entries[-30:]:
            flag = green("Yes") if e.get("had_changes") else dim("No ")
            print(f"  {e['date']:<14} {flag}")
    print()
    ask("Press Enter to continue")


def main(args):
    today = date.fromisoformat(args.date) if args.date else date.today()
    mem   = load_memory()
    log   = load_log()

    if args.update:
        self_update()
        return

    while True:
        print_menu()
        choice = ask(f"Enter your choice (1-{len(MENU_ITEMS)})")
        if not choice.isdigit() or not (1 <= int(choice) <= len(MENU_ITEMS)):
            warn(f"Please enter a number between 1 and {len(MENU_ITEMS)}."); continue
        c = int(choice)
        if   c == 1: generate_import(mem, log, today, catchup=args.catchup)
        elif c == 2: manage_mappings_menu(mem)
        elif c == 3:
            section("ADD SHORTCUT TO DESKTOP")
            add_to_desktop()
            ask("\nPress Enter to continue")
        elif c == 4: view_run_history(log)
        elif c == 5: self_update()
        elif c == 6: print(); info("Goodbye!"); break


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Skyward -> Eduphoria Role Importer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--catchup", action="store_true",
                        help="Automatically catch up missed days without prompting")
    parser.add_argument("--date",    metavar="YYYY-MM-DD",
                        help="Treat this date as 'today' (for testing)")
    parser.add_argument("--update",  action="store_true",
                        help="Check for and apply updates, then exit")
    main(parser.parse_args())
