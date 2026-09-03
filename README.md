# Employee Management System

A Python employee management system with **three interchangeable front
ends** — a terminal menu, a web app, and a desktop GUI — all sharing one
SQLite database (`ems_data.db`) and one set of business-logic modules
in `ems/`. Use whichever fits the moment; data stays in sync across all
three since they read/write the same file.

| Front end | Run | Needs |
|---|---|---|
| **Web app** (`app.py`) | `python3 app.py`, open `http://127.0.0.1:5000` | `pip install flask` |
| **Desktop GUI** (`desktop_app.py`) | `python3 desktop_app.py` | `tkinter` (see below) |
| **Terminal CLI** (`main.py`) | `python3 main.py` | nothing extra |

## Features

- **Employees** — add, edit, deactivate/reactivate, delete; store name,
  position, department, EFT, hire date, contact info.
- **EFT (Employment Full-Time equivalent)** — e.g. `1.0` = full time,
  `0.5` = half time. Used to calculate each employee's expected monthly
  hours in reports.
- **Shift types** — define reusable shifts (e.g. Morning 07:00–15:00);
  hours are calculated automatically, including overnight shifts.
- **Monthly schedule** — assign employees to shifts by date; view by day,
  by employee/month, or as a full staffing calendar. Each employee also
  has their own monthly calendar view (an actual Mon–Sun grid, not just
  a list) showing their shifts at a glance.
- **Employee roster grouping** — browse the employee list grouped by
  department, or by shift type (each employee's most common shift, taken
  from their active recurring patterns or, failing that, their most
  frequent shift this month) — useful once you have more than a handful
  of employees.
- **Recurring shift patterns** — set a pattern once (e.g. "Jane works
  Morning every Mon–Fri starting Aug 1", or "John works Night every other
  Saturday, rotation week 1, starting Aug 1") and the schedule fills
  itself in automatically. Every time you open any of the three front
  ends — and every time a relevant page is viewed in the web app, even
  on a long-running server — the current month and the month right after
  it are auto-generated from active patterns (e.g. in August that's
  August + September; in September it's September + October). This
  never reaches further out automatically; to fill in a month beyond
  that from active patterns, use the explicit "Generate a Specific
  Month" action on the Patterns page (or the equivalent CLI/desktop
  option), which works for any month on request. You can stop a pattern
  (keeps history, halts future months) or delete it outright at any time.
- **Sick / absence tracking** — record absences (Sick/Personal/Vacation/
  Unpaid/Other), link them to the missed shift, and record who covered
  it. The linked schedule entry is automatically updated to "Absent" or
  "Covered", and the absence's hours are pulled automatically from that
  shift's length — no manual hour entry needed. Marking a shift "Absent"
  or "Covered" from *either* the quick status control on the Schedule
  page or the full "Record an Absence" form keeps the absences table and
  the schedule in sync automatically — hours are counted correctly no
  matter which one you use, and switching a shift back to
  Scheduled/Worked cleanly removes the leave record so it isn't
  double-counted. Whoever covers a shift gets it reflected as a real
  entry on *their own* calendar too, so it's visible there like any other
  shift — adding, changing, or removing who covered it (or deleting the
  absence record entirely) keeps that entry, and the original employee's
  Absent/Covered mark, in sync automatically. Existing absence records
  can be edited from the Absences log (web app) — including moving one
  to a different employee or date, which correctly reverts the old
  shift's mark and re-links to the new one.
- **Employee search on Overtime and Absences** (web app) — a
  type-to-search picker instead of a plain dropdown for choosing the
  employee (and, on Absences, who covered a shift), so finding the right
  person in a roster of hundreds or thousands stays fast.
- **Overtime (OT)** — two sources, combined automatically: manual entries
  you log yourself (reason, who approved it), and auto-detected overtime
  computed from actual hours worked (an employee's own shifts plus any
  hours they picked up covering a colleague). Daily OT is figured per
  shift — an 8-hour shift and a 12-hour shift each set their own no-OT
  baseline for that day automatically, so mixed shift lengths need no
  configuration. Biweekly OT applies over a 14-day pay period (default
  80h). Thresholds are adjustable in `ems/reports.py`. It doesn't matter
  whether the extra hours came from a double shift or from covering
  someone else's absence — payroll only cares how many hours were
  actually worked. Manually-logged OT also shows up on the employee's own
  calendar in the web app, live from the Overtime records each time the
  calendar is viewed — deleting an OT entry removes it from the calendar
  automatically, no extra step needed.
- **Individual hours reports** — for any employee and month: total hours
  worked (including hours picked up covering someone else's shift), sick/
  personal/vacation/unpaid/other leave hours, OT hours, total paid
  hours, and their full day-by-day schedule — all computed automatically
  from the schedule/absence/overtime records, so it's always current.
- **Reports** — a monthly overview across all active employees (worked/
  sick/OT/total-paid hours vs. EFT-expected hours) with a link into each
  employee's full individual breakdown, plus a quick staffing-overview
  calendar. Every employee's monthly summary can be exported to a single
  Excel workbook (one row per employee, all the same figures shown on
  the Reports page) — an "Export to Excel" button on the web Reports
  page, an "Export to Excel" button on the desktop Reports tab, or
  option 4 in the CLI's Reports menu.

## Requirements

- Python 3.8+
- The CLI (`main.py`) needs `openpyxl` for the Excel export (`pip install openpyxl --break-system-packages` if needed) — otherwise nothing beyond the standard library.
- The **web app** needs Flask and openpyxl: `pip install flask openpyxl` (or `pip install flask openpyxl --break-system-packages` on newer Debian/Ubuntu systems that block global pip installs).
- The **desktop GUI** needs `tkinter` and `openpyxl`. If you get `ModuleNotFoundError: No module named 'tkinter'`:
  - **Ubuntu/Debian**: `sudo apt-get install python3-tk`
  - **macOS (python.org installer)**: included by default; with Homebrew Python, run `brew install python-tk`
  - **Windows**: included by default with the standard installer

## Running

**Web app** (recommended for a manager who wants to work from a browser, or have several people use it on a local network):
```bash
python3 app.py
```
Then open `http://127.0.0.1:5000`. To let other devices on your network reach it, change the last line of `app.py` to `app.run(host="0.0.0.0", port=5000)` and open `http://<your-computer's-IP>:5000` from another device.

**Desktop GUI** (a standalone app window, no browser needed):
```bash
python3 desktop_app.py
```

**Terminal CLI** (fastest for quick data entry or scripting):
```bash
python3 main.py
```

Any of the three will create `ems_data.db` in this folder on first run
and seed three default shift types (Morning / Evening / Night), which
you can edit or delete from the Shift Types page/menu.

## Project structure

```
employee_management_system/
├── main.py              # terminal CLI entry point
├── app.py                # Flask web app entry point
├── desktop_app.py       # Tkinter desktop GUI entry point
├── ems_data.db           # SQLite database (created on first run)
├── templates/            # HTML templates for the web app
├── static/style.css      # web app styling
└── ems/
    ├── database.py       # schema + connection helper
    ├── employees.py       # employee CRUD
    ├── shifts.py           # shift type definitions
    ├── schedule.py       # assigning/viewing the monthly schedule
    ├── recurring.py       # recurring weekly/biweekly patterns → auto-generates schedule
    ├── absences.py       # sick/absence + coverage tracking (with hours)
    ├── overtime.py       # manual OT tracking
    ├── reports.py       # individual & all-employee hours breakdowns
    └── exports.py       # Excel (.xlsx) export of monthly hours summaries
```

All three front ends are thin — they call the same functions in `ems/`.
If you add a feature to `ems/`, it's a small amount of wiring to expose
it in each interface.

## Using it as a library

Every menu action is backed by plain functions in the `ems` package, so
you can script it or build another interface (web, GUI) on top without
touching the CLI. For example:

```python
from ems.database import initialize_database
from ems import employees as emp, schedule as sc

initialize_database()
emp.add_employee("E001", "Jane", "Doe", position="Nurse", eft=1.0,
                  hire_date="2023-01-15")
e = emp.find_employee_by_code("E001")
sc.assign_shift(e["id"], shift_type_id=1, work_date="2026-08-01")
```

## Notes / things you may want to customize

- `STANDARD_FULL_TIME_HOURS_PER_MONTH` in `ems/reports.py` (default 173,
  ~40 hrs/week average) is used to compute each employee's EFT-based
  expected monthly hours — adjust to match your organization's standard.
- The database file `ems_data.db` is plain SQLite — you can open it with
  any SQLite browser (e.g. DB Browser for SQLite) if you want a GUI view
  of the raw data alongside the CLI.
- Deleting an employee permanently cascades and removes their schedule,
  absence, and OT records too. Deactivating instead just flags them
  Inactive and keeps all history.
