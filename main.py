#!/usr/bin/env python3
"""
Employee Management System
---------------------------
A menu-driven CLI for managing employees, shift types, monthly schedules,
sick/absence tracking (with shift coverage), and overtime (OT).

Run:  python3 main.py
Data is stored locally in ems_data.db (SQLite) in this folder.
"""

import sys
from datetime import datetime

from ems.database import initialize_database
from ems import employees as emp
from ems import shifts as sh
from ems import schedule as sc
from ems import absences as ab
from ems import overtime as ot
from ems import reports as rp
from ems import recurring as rec
from ems import exports as exp


# ---------------------------------------------------------------- helpers --

def pause():
    input("\nPress Enter to continue...")


def prompt(text, default=None, required=True):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"{text}{suffix}: ").strip()
        if not val and default is not None:
            return default
        if not val and not required:
            return ""
        if val:
            return val
        print("This field is required.")


def prompt_float(text, default=None):
    while True:
        raw = prompt(text, default=str(default) if default is not None else None)
        try:
            return float(raw)
        except ValueError:
            print("Please enter a valid number.")


def prompt_date(text, default=None):
    while True:
        raw = prompt(text, default=default)
        try:
            datetime.strptime(raw, "%Y-%m-%d")
            return raw
        except ValueError:
            print("Please enter a date as YYYY-MM-DD.")


def prompt_time(text, default=None):
    while True:
        raw = prompt(text, default=default)
        try:
            datetime.strptime(raw, "%H:%M")
            return raw
        except ValueError:
            print("Please enter a time as HH:MM (24-hour).")


def prompt_int(text, default=None):
    while True:
        raw = prompt(text, default=str(default) if default is not None else None)
        try:
            return int(raw)
        except ValueError:
            print("Please enter a whole number.")


def choose_employee(prompt_text="Employee code"):
    code = prompt(prompt_text)
    e = emp.find_employee_by_code(code)
    if not e:
        print("No employee found with that code.")
        return None
    return e


def print_table(rows, columns):
    """columns: list of (header, key, width)"""
    if not rows:
        print("(no records found)")
        return
    header = " | ".join(f"{h:<{w}}" for h, _, w in columns)
    print(header)
    print("-" * len(header))
    for r in rows:
        line = " | ".join(f"{str(r.get(k, '')):<{w}}" for _, k, w in columns)
        print(line)


def print_employee_calendar(employee, year, month):
    """Print one employee's schedule as an actual month calendar grid
    (Mon-first weeks), with each day's shift(s) and status abbreviated."""
    weeks = rp.employee_monthly_calendar_grid(employee["id"], year, month)
    label = f"{employee['first_name']} {employee['last_name']} ({employee['employee_code']}) — {rp.month_name(year, month)}"
    print(f"\n{label}")
    print("=" * len(label))
    col_w = 16
    print(" | ".join(f"{d:<{col_w}}" for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]))
    print("-" * (col_w * 7 + 3 * 6))
    for week in weeks:
        day_line = []
        detail_lines = [[] for _ in range(3)]  # up to 3 shift lines per day
        for day in week:
            if day is None:
                day_line.append(" " * col_w)
                for dl in detail_lines:
                    dl.append(" " * col_w)
                continue
            day_line.append(f"{day['day']:<{col_w}}")
            entries = day["entries"][:3]
            for i in range(3):
                if i < len(entries):
                    e = entries[i]
                    text = f"{e['shift_name'][:8]} ({e['status'][:3]})"
                else:
                    text = ""
                detail_lines[i].append(f"{text:<{col_w}}")
        print(" | ".join(day_line))
        for dl in detail_lines:
            if any(cell.strip() for cell in dl):
                print(" | ".join(dl))
        print()


# ---------------------------------------------------------- employee menu --

def menu_employees():
    while True:
        print("\n--- Employee Management ---")
        print("1. Add employee")
        print("2. List / search employees (optionally grouped)")
        print("3. Edit employee")
        print("4. Deactivate employee")
        print("5. Reactivate employee")
        print("6. Delete employee permanently")
        print("7. View an employee's monthly calendar")
        print("0. Back to main menu")
        choice = prompt("Choose an option", required=True)

        if choice == "1":
            code = prompt("Employee code (unique, e.g. E001)")
            first = prompt("First name")
            last = prompt("Last name")
            position = prompt("Position", required=False)
            department = prompt("Department", required=False)
            eft = prompt_float("EFT (1.0 = full time, 0.5 = half time)", default=1.0)
            hire_date = prompt_date("Hire date (YYYY-MM-DD)", default=datetime.today().strftime("%Y-%m-%d"))
            phone = prompt("Phone", required=False)
            email = prompt("Email", required=False)
            ok, msg = emp.add_employee(code, first, last, position, department,
                                        eft, hire_date, phone, email)
            print(msg)

        elif choice == "2":
            status = prompt("Filter by status (Active/Inactive/blank for all)", required=False)
            search = prompt("Search name or code (blank for none)", required=False)
            group_by = prompt("Group by (department/shift_type/blank for flat list)", required=False)

            if group_by in ("department", "shift_type"):
                for label, rows in emp.list_employees_grouped(group_by=group_by, status=status or None,
                                                                search=search or None):
                    print(f"\n== {label} ({len(rows)}) ==")
                    print_table(rows, [
                        ("Code", "employee_code", 8), ("First", "first_name", 12),
                        ("Last", "last_name", 12), ("Position", "position", 14),
                        ("EFT", "eft", 5), ("Status", "status", 9),
                    ])
            else:
                rows = emp.list_employees(status=status or None, search=search or None)
                print_table(rows, [
                    ("Code", "employee_code", 8), ("First", "first_name", 12),
                    ("Last", "last_name", 12), ("Position", "position", 14),
                    ("EFT", "eft", 5), ("Status", "status", 9),
                ])

        elif choice == "3":
            e = choose_employee()
            if e:
                print("Leave blank to keep current value.")
                first = prompt("First name", default=e["first_name"])
                last = prompt("Last name", default=e["last_name"])
                position = prompt("Position", default=e["position"] or "", required=False)
                department = prompt("Department", default=e["department"] or "", required=False)
                eft = prompt_float("EFT", default=e["eft"])
                phone = prompt("Phone", default=e["phone"] or "", required=False)
                email = prompt("Email", default=e["email"] or "", required=False)
                ok, msg = emp.update_employee(e["id"], first_name=first, last_name=last,
                                               position=position, department=department,
                                               eft=eft, phone=phone, email=email)
                print(msg)

        elif choice == "4":
            e = choose_employee()
            if e:
                ok, msg = emp.deactivate_employee(e["id"])
                print(msg)

        elif choice == "5":
            e = choose_employee()
            if e:
                ok, msg = emp.reactivate_employee(e["id"])
                print(msg)

        elif choice == "6":
            e = choose_employee()
            if e:
                confirm = prompt(f"Type DELETE to permanently remove {e['first_name']} {e['last_name']}",
                                  required=False)
                if confirm == "DELETE":
                    ok, msg = emp.delete_employee(e["id"])
                    print(msg)
                else:
                    print("Cancelled.")

        elif choice == "7":
            e = choose_employee()
            if not e:
                pause()
                continue
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            rec.generate_schedule_for_month_if_within_window(year, month)
            print_employee_calendar(e, year, month)

        elif choice == "0":
            return
        else:
            print("Invalid option.")
        pause()


# ------------------------------------------------------------- shift menu --

def menu_shifts():
    while True:
        print("\n--- Shift Types ---")
        print("1. Add shift type")
        print("2. List shift types")
        print("3. Edit shift type")
        print("4. Delete shift type")
        print("0. Back to main menu")
        choice = prompt("Choose an option")

        if choice == "1":
            name = prompt("Shift name (e.g. Morning, Evening, Night)")
            start = prompt_time("Start time (HH:MM)")
            end = prompt_time("End time (HH:MM)")
            ok, msg = sh.add_shift_type(name, start, end)
            print(msg)

        elif choice == "2":
            rows = sh.list_shift_types()
            print_table(rows, [
                ("ID", "id", 4), ("Name", "name", 12),
                ("Start", "start_time", 7), ("End", "end_time", 7), ("Hours", "hours", 6),
            ])

        elif choice == "3":
            rows = sh.list_shift_types()
            print_table(rows, [("ID", "id", 4), ("Name", "name", 12),
                                ("Start", "start_time", 7), ("End", "end_time", 7)])
            sid = prompt_int("Shift type ID to edit")
            existing = sh.get_shift_type(sid)
            if not existing:
                print("Not found.")
            else:
                name = prompt("Name", default=existing["name"])
                start = prompt_time("Start time", default=existing["start_time"])
                end = prompt_time("End time", default=existing["end_time"])
                ok, msg = sh.update_shift_type(sid, name, start, end)
                print(msg)

        elif choice == "4":
            sid = prompt_int("Shift type ID to delete")
            ok, msg = sh.delete_shift_type(sid)
            print(msg)

        elif choice == "0":
            return
        else:
            print("Invalid option.")
        pause()


# --------------------------------------------------- recurring pattern menu --

def menu_patterns():
    while True:
        print("\n--- Recurring Shift Patterns ---")
        print("Set a weekly pattern once and the schedule fills itself in every month.")
        print("1. Add recurring pattern")
        print("2. List patterns")
        print("3. Stop a pattern (keeps history, stops future months)")
        print("4. Delete a pattern")
        print("5. Generate schedule for a month now")
        print("0. Back to main menu")
        choice = prompt("Choose an option")

        if choice == "1":
            e = choose_employee()
            if not e:
                pause()
                continue
            rows = sh.list_shift_types()
            print_table(rows, [("ID", "id", 4), ("Name", "name", 12),
                                ("Start", "start_time", 7), ("End", "end_time", 7)])
            sid = prompt_int("Shift type ID")
            print("Weekday: 0=Monday 1=Tuesday 2=Wednesday 3=Thursday 4=Friday 5=Saturday 6=Sunday")
            weekday = prompt_int("Weekday (0-6)")
            freq_raw = prompt("Frequency: (w)eekly or (b)iweekly [every other week]", default="w")
            frequency = "biweekly" if freq_raw.lower().startswith("b") else "weekly"
            biweekly_week = 1
            if frequency == "biweekly":
                biweekly_week = prompt_int("Rotation week (1 or 2 — pick 1 for the same week as the start date)", default=1)
            start = prompt_date("Starting from (YYYY-MM-DD)", default=datetime.today().strftime("%Y-%m-%d"))
            end_raw = prompt("Ending on (YYYY-MM-DD, blank = ongoing)", required=False)
            end = end_raw or None
            notes = prompt("Notes", required=False)
            ok, msg = rec.add_pattern(e["id"], sid, weekday, start, end,
                                       frequency=frequency, biweekly_week=biweekly_week, notes=notes)
            print(msg)
            print("Tip: for a full Mon-Fri pattern, add one entry per weekday.")

        elif choice == "2":
            rows = rec.list_patterns()
            for r in rows:
                if r.get("frequency") == "biweekly":
                    r["weekday_name"] = f"Every other {rec.WEEKDAY_NAMES[r['weekday']]} (wk{r.get('biweekly_week', 1)})"
                else:
                    r["weekday_name"] = f"Every {rec.WEEKDAY_NAMES[r['weekday']]}"
                r["status_label"] = "Active" if r["active"] else "Stopped"
                r["effective_end"] = r["effective_end"] or "ongoing"
            print_table(rows, [
                ("ID", "id", 4), ("Employee", "last_name", 12), ("Shift", "shift_name", 10),
                ("Repeats", "weekday_name", 24), ("From", "effective_start", 12),
                ("Until", "effective_end", 12), ("Status", "status_label", 8),
            ])

        elif choice == "3":
            pid = prompt_int("Pattern ID to stop")
            ok, msg = rec.deactivate_pattern(pid)
            print(msg)

        elif choice == "4":
            pid = prompt_int("Pattern ID to delete")
            ok, msg = rec.delete_pattern(pid)
            print(msg)

        elif choice == "5":
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            created = rec.generate_schedule_for_month(year, month)
            print(f"Generated {created} new schedule entries from active patterns "
                  f"(existing entries were left untouched). This is an explicit generate — "
                  f"unlike automatic generation, it works for any month, not just current/next.")

        elif choice == "0":
            return
        else:
            print("Invalid option.")
        pause()


# ---------------------------------------------------------- schedule menu --

def menu_schedule():
    while True:
        print("\n--- Monthly Schedule ---")
        print("1. Assign shift to employee")
        print("2. View schedule for a date")
        print("3. View schedule for employee (month)")
        print("4. View full monthly schedule")
        print("5. Update / cancel a schedule entry")
        print("0. Back to main menu")
        choice = prompt("Choose an option")

        if choice == "1":
            e = choose_employee()
            if not e:
                pause()
                continue
            rows = sh.list_shift_types()
            print_table(rows, [("ID", "id", 4), ("Name", "name", 12),
                                ("Start", "start_time", 7), ("End", "end_time", 7)])
            sid = prompt_int("Shift type ID")
            date = prompt_date("Work date (YYYY-MM-DD)")
            ok, msg = sc.assign_shift(e["id"], sid, date)
            print(msg)

        elif choice == "2":
            date = prompt_date("Date (YYYY-MM-DD)")
            rows = sc.get_schedule_for_date(date)
            print_table(rows, [
                ("ID", "id", 4), ("Code", "employee_code", 8), ("First", "first_name", 10),
                ("Last", "last_name", 10), ("Shift", "shift_name", 10), ("Status", "status", 10),
            ])

        elif choice == "3":
            e = choose_employee()
            if not e:
                pause()
                continue
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            rows = sc.get_schedule_for_employee_month(e["id"], year, month)
            print_table(rows, [
                ("ID", "id", 4), ("Date", "work_date", 12), ("Shift", "shift_name", 10),
                ("Hours", "hours", 6), ("Status", "status", 10),
            ])
            print(f"Total scheduled hours: {sc.total_scheduled_hours(e['id'], year, month)}")

        elif choice == "4":
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            print(rp.print_monthly_calendar(year, month))

        elif choice == "5":
            sid = prompt_int("Schedule entry ID")
            print("Status options: Scheduled / Worked / Absent")
            print("(Personal/Vacation/Other reasons or coverage: use Sick/Absence menu instead — it stays in sync)")
            status = prompt("New status")
            reason = "Sick"
            if status == "Absent":
                reason = prompt("Reason (Sick/Personal/Vacation/Other)", default="Sick")
            ok, msg = sc.set_status_with_sync(sid, status, reason=reason)
            print(msg)

        elif choice == "0":
            return
        else:
            print("Invalid option.")
        pause()


# ---------------------------------------------------------- absence menu --

def menu_absences():
    while True:
        print("\n--- Sick / Absence & Coverage Tracking ---")
        print("1. Record an absence")
        print("2. Assign / change who covered an absence")
        print("3. List absences (employee)")
        print("4. List absences (month, all employees)")
        print("5. Absence summary by employee")
        print("0. Back to main menu")
        choice = prompt("Choose an option")

        if choice == "1":
            e = choose_employee("Absent employee code")
            if not e:
                pause()
                continue
            date = prompt_date("Absence date (YYYY-MM-DD)")
            reason = prompt("Reason (Sick/Personal/Vacation/Other)", default="Sick")

            sid_raw = prompt("Linked schedule entry ID (blank if none)", required=False)
            schedule_id = int(sid_raw) if sid_raw else None

            has_cover = prompt("Was the shift covered by someone? (y/n)", default="n")
            covered_id = None
            if has_cover.lower() == "y":
                cover = choose_employee("Covering employee code")
                if cover:
                    covered_id = cover["id"]

            notes = prompt("Notes", required=False)
            ok, msg = ab.record_absence(e["id"], date, reason, schedule_id, covered_id, notes)
            print(msg)

        elif choice == "2":
            aid = prompt_int("Absence record ID")
            cover = choose_employee("Covering employee code")
            if cover:
                ok, msg = ab.set_coverage(aid, cover["id"])
                print(msg)

        elif choice == "3":
            e = choose_employee()
            if not e:
                pause()
                continue
            rows = ab.list_absences(employee_id=e["id"])
            print_table(rows, [
                ("ID", "id", 4), ("Date", "absence_date", 12), ("Reason", "reason", 10),
                ("Covered By", "covered_code", 10),
            ])

        elif choice == "4":
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            rows = ab.list_absences(year=year, month=month)
            print_table(rows, [
                ("ID", "id", 4), ("Date", "absence_date", 12), ("Code", "employee_code", 8),
                ("Reason", "reason", 10), ("Covered By", "covered_code", 10),
            ])

        elif choice == "5":
            year_raw = prompt("Year (blank for all-time)", required=False)
            month_raw = prompt("Month (blank for all-time)", required=False)
            year = int(year_raw) if year_raw else None
            month = int(month_raw) if month_raw else None
            rows = ab.absence_summary_by_employee(year, month)
            print_table(rows, [
                ("Code", "employee_code", 8), ("First", "first_name", 10),
                ("Last", "last_name", 10), ("Absences", "absence_count", 9),
            ])

        elif choice == "0":
            return
        else:
            print("Invalid option.")
        pause()


# ------------------------------------------------------------- OT menu --

def menu_overtime():
    while True:
        print("\n--- Overtime (OT) Tracking ---")
        print("1. Record overtime")
        print("2. Delete overtime record")
        print("3. List overtime (employee)")
        print("4. List overtime (month, all employees)")
        print("5. Overtime summary by employee")
        print("0. Back to main menu")
        choice = prompt("Choose an option")

        if choice == "1":
            e = choose_employee()
            if not e:
                pause()
                continue
            date = prompt_date("OT date (YYYY-MM-DD)")
            hours = prompt_float("OT hours")
            reason = prompt("Reason", required=False)
            approved_by = prompt("Approved by", required=False)
            notes = prompt("Notes", required=False)
            ok, msg = ot.record_overtime(e["id"], date, hours, reason, approved_by, notes)
            print(msg)

        elif choice == "2":
            oid = prompt_int("Overtime record ID to delete")
            ok, msg = ot.delete_overtime(oid)
            print(msg)

        elif choice == "3":
            e = choose_employee()
            if not e:
                pause()
                continue
            rows = ot.list_overtime(employee_id=e["id"])
            print_table(rows, [
                ("ID", "id", 4), ("Date", "ot_date", 12), ("Hours", "hours", 6),
                ("Reason", "reason", 14), ("Approved By", "approved_by", 12),
            ])

        elif choice == "4":
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            rows = ot.list_overtime(year=year, month=month)
            print_table(rows, [
                ("ID", "id", 4), ("Date", "ot_date", 12), ("Code", "employee_code", 8),
                ("Hours", "hours", 6), ("Reason", "reason", 14),
            ])

        elif choice == "5":
            year_raw = prompt("Year (blank for all-time)", required=False)
            month_raw = prompt("Month (blank for all-time)", required=False)
            year = int(year_raw) if year_raw else None
            month = int(month_raw) if month_raw else None
            rows = ot.overtime_summary_by_employee(year, month)
            print_table(rows, [
                ("Code", "employee_code", 8), ("First", "first_name", 10),
                ("Last", "last_name", 10), ("Total OT Hrs", "total_ot_hours", 12),
            ])

        elif choice == "0":
            return
        else:
            print("Invalid option.")
        pause()


# ---------------------------------------------------------- reports menu --

def menu_reports():
    while True:
        print("\n--- Reports ---")
        print("1. Individual employee hours (worked, sick, OT, full schedule)")
        print("2. All active employees monthly summary")
        print("3. Monthly staffing overview (calendar view)")
        print("4. Export all active employees' monthly summary to Excel")
        print("0. Back to main menu")
        choice = prompt("Choose an option")

        if choice == "1":
            e = choose_employee()
            if not e:
                pause()
                continue
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            rec.generate_schedule_for_month_if_within_window(year, month)  # keep this month current
            data = rp.employee_hours_breakdown(e["id"], year, month)

            print(f"\n{data['employee']['first_name']} {data['employee']['last_name']} "
                  f"({data['employee']['employee_code']}) — {data['month_label']}")
            print("-" * 60)
            print(f"{'Expected hours (EFT ' + str(data['employee']['eft']) + ')':<38}: {data['expected_hours']}")
            print(f"{'Worked hours (own shifts + covering others)':<38}: {data['worked_hours']}")
            print(f"{'  of which, covering someone else':<38}: {data['coverage_given_hours']}")
            print(f"{'Covered by someone else (not worked)':<38}: {data['covered_away_hours']}")
            print(f"{'Absent, uncovered':<38}: {data['absent_hours']}")
            print(f"{'Sick leave hours':<38}: {data['sick_hours']}")
            print(f"{'Personal leave hours':<38}: {data['personal_hours']}")
            print(f"{'Vacation hours':<38}: {data['vacation_hours']}")
            print(f"{'Other leave hours':<38}: {data['other_leave_hours']}")
            print(f"{'Unpaid leave hours':<38}: {data['unpaid_leave_hours']}")
            print(f"{'Total leave hours':<38}: {data['total_leave_hours']}")
            print(f"{'Overtime — manual entries':<38}: {data['manual_overtime_hours']}")
            print(f"{'  auto-detected (daily)':<38}: {data['auto_overtime_daily']}")
            print(f"{'  auto-detected (biweekly, >80h/14d)':<38}: {data['auto_overtime_biweekly']}")
            print(f"{'Total overtime':<38}: {data['overtime_hours']}")
            print(f"{'TOTAL PAID HOURS':<38}: {data['total_paid_hours']}")

            show_sched = prompt("\nShow full day-by-day schedule for this month? (y/n)", default="n")
            if show_sched.lower() == "y":
                print_table(data["schedule_entries"], [
                    ("Date", "work_date", 12), ("Shift", "shift_name", 10),
                    ("Time", "start_time", 6), ("Hours", "hours", 6), ("Status", "status", 10),
                ])

        elif choice == "2":
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            rec.generate_schedule_for_month_if_within_window(year, month)
            rows = []
            for e in emp.list_employees(status="Active"):
                d = rp.employee_hours_breakdown(e["id"], year, month)
                d["name"] = f"{d['employee']['first_name']} {d['employee']['last_name']}"
                rows.append(d)
            print_table(rows, [
                ("Name", "name", 18), ("Worked Hrs", "worked_hours", 11),
                ("Sick Hrs", "sick_hours", 9), ("OT Hrs", "overtime_hours", 8),
                ("Total Paid", "total_paid_hours", 11),
            ])

        elif choice == "4":
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            default_name = f"employee-hours-{year:04d}-{month:02d}.xlsx"
            out_path = prompt("Save to file path", default=default_name)
            try:
                exp.export_monthly_summary_to_excel(year, month, out_path)
                print(f"Exported to: {out_path}")
            except Exception as e:
                print(f"Export failed: {e}")

        elif choice == "3":
            year = prompt_int("Year", default=datetime.today().year)
            month = prompt_int("Month (1-12)", default=datetime.today().month)
            print(rp.print_monthly_calendar(year, month))

        elif choice == "0":
            return
        else:
            print("Invalid option.")
        pause()


# -------------------------------------------------------------- main loop --

def seed_defaults_if_empty():
    """Add a few common shift types on first run so the system is usable
    right away. Safe to skip/edit later."""
    if not sh.list_shift_types():
        sh.add_shift_type("Morning", "07:00", "15:00")
        sh.add_shift_type("Evening", "15:00", "23:00")
        sh.add_shift_type("Night", "23:00", "07:00")


def main():
    initialize_database()
    seed_defaults_if_empty()

    # Auto-generate the schedule from recurring patterns for the current
    # month and one month ahead, every time the program starts — this is
    # what keeps each employee's monthly schedule building itself forward
    # automatically without manual re-entry, never further than one month out.
    rec.generate_current_and_next_month()

    while True:
        print("\n===== EMPLOYEE MANAGEMENT SYSTEM =====")
        print("1. Employees")
        print("2. Shift Types")
        print("3. Recurring Patterns (auto-generates monthly schedule)")
        print("4. Monthly Schedule")
        print("5. Sick / Absence & Coverage")
        print("6. Overtime (OT)")
        print("7. Reports")
        print("0. Exit")
        choice = prompt("Choose an option")

        if choice == "1":
            menu_employees()
        elif choice == "2":
            menu_shifts()
        elif choice == "3":
            menu_patterns()
        elif choice == "4":
            menu_schedule()
        elif choice == "5":
            menu_absences()
        elif choice == "6":
            menu_overtime()
        elif choice == "7":
            menu_reports()
        elif choice == "0":
            print("Goodbye!")
            sys.exit(0)
        else:
            print("Invalid option, please try again.")


if __name__ == "__main__":
    main()
