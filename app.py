#!/usr/bin/env python3
"""
app.py — Web front end (Flask) for the Employee Management System.

Run:
    python3 app.py
Then open http://127.0.0.1:5000 in a browser.

This is a thin presentation layer over the same `ems` package used by
the CLI (main.py) and the desktop GUI (desktop_app.py) — all three share
one SQLite database (ems_data.db) and one set of business-logic modules.
"""

import calendar
import os
import tempfile
import threading
import webbrowser
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, send_file

from ems.database import initialize_database
from ems import employees as emp
from ems import shifts as sh
from ems import schedule as sc
from ems import absences as ab
from ems import overtime as ot
from ems import reports as rp
from ems import recurring as rec
from ems import exports as exp

app = Flask(__name__)
app.secret_key = "dev-key-change-if-deploying-publicly"

initialize_database()
if not sh.list_shift_types():
    sh.add_shift_type("Morning", "07:00", "15:00")
    sh.add_shift_type("Evening", "15:00", "23:00")
    sh.add_shift_type("Night", "23:00", "07:00")

# Auto-generate the schedule from recurring patterns for the current month
# and one month ahead, every time the app starts — this is what keeps each
# employee's monthly schedule building itself forward automatically, and
# never further than one month out.
rec.generate_current_and_next_month()


def today_str():
    return datetime.today().strftime("%Y-%m-%d")


def cur_year_month():
    t = datetime.today()
    return t.year, t.month


def employee_search_options(status="Active"):
    """[{id, label}, ...] for the type-to-search employee picker used on
    the Overtime and Absences pages — built once per request from
    whichever employees are relevant, so the search box works entirely
    client-side (no per-keystroke server round trip) even with a large
    roster."""
    return [
        {"id": e["id"], "label": f"{e['first_name']} {e['last_name']} ({e['employee_code']})"}
        for e in emp.list_employees(status=status)
    ]


# ============================================================ dashboard =

@app.route("/")
def dashboard():
    date = today_str()
    year, month = cur_year_month()
    rec.generate_schedule_for_month_if_within_window(year, month)  # only auto-fills current/next month

    todays_shifts = sc.get_schedule_for_date(date)
    summaries = rp.all_employees_monthly_summary(year, month)

    active_count = len(emp.list_employees(status="Active"))
    absences_today = [a for a in ab.list_absences() if a["absence_date"] == date]
    ot_month = ot.overtime_summary_by_employee(year, month)
    total_ot = round(sum(r["total_ot_hours"] for r in ot_month), 1)

    schedule_by_date = sc.get_monthly_schedule(year, month)
    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(None)
                continue
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            count = len(schedule_by_date.get(date_str, []))
            row.append({"day": day, "count": count})
        weeks.append(row)

    return render_template(
        "dashboard.html", active="dashboard",
        today=date, todays_shifts=todays_shifts, active_count=active_count,
        absences_today=absences_today, total_ot=total_ot,
        month_name=rp.month_name(year, month), weeks=weeks,
        year=year, month=month,
    )


# ============================================================ employees =

@app.route("/employees")
def employees():
    status = request.args.get("status", "")
    search = request.args.get("q", "")
    filter_by = request.args.get("filter_by", "")
    filter_value = request.args.get("filter_value", "")

    rows = emp.list_employees(status=status or None, search=search or None)

    if filter_by == "department" and filter_value:
        rows = [e for e in rows if (e.get("department") or "").strip().lower() == filter_value.strip().lower()]
    elif filter_by == "shift_type" and filter_value:
        rows = [
            e for e in rows
            if (emp.primary_shift_for_employee(e["id"]) or {}).get("name") == filter_value
        ]

    department_options = sorted({
        e.get("department") for e in rows if e.get("department")
    })
    shift_options = sorted({
        (emp.primary_shift_for_employee(e["id"]) or {}).get("name")
        for e in rows if (emp.primary_shift_for_employee(e["id"]) or {}).get("name")
    })

    return render_template("employees.html", active="employees",
                            employees=rows, groups=None,
                            status=status, search=search,
                            filter_by=filter_by, filter_value=filter_value,
                            department_options=department_options,
                            shift_options=shift_options)


@app.route("/employees/new", methods=["GET", "POST"])
def employee_new():
    if request.method == "POST":
        ok, msg = emp.add_employee(
            employee_code=request.form["employee_code"].strip(),
            first_name=request.form["first_name"].strip(),
            last_name=request.form["last_name"].strip(),
            position=request.form.get("position", "").strip(),
            department=request.form.get("department", "").strip(),
            eft=float(request.form.get("eft") or 1.0),
            hire_date=request.form.get("hire_date", "").strip(),
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
        )
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("employees"))
    return render_template("employee_form.html", active="employees",
                            employee=None, today=today_str())


@app.route("/employees/<int:employee_id>/edit", methods=["GET", "POST"])
def employee_edit(employee_id):
    employee = emp.get_employee(employee_id)
    if not employee:
        flash("Employee not found.", "error")
        return redirect(url_for("employees"))

    if request.method == "POST":
        ok, msg = emp.update_employee(
            employee_id,
            first_name=request.form["first_name"].strip(),
            last_name=request.form["last_name"].strip(),
            position=request.form.get("position", "").strip(),
            department=request.form.get("department", "").strip(),
            eft=float(request.form.get("eft") or 1.0),
            hire_date=request.form.get("hire_date", "").strip(),
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
        )
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("employees"))

    return render_template("employee_form.html", active="employees",
                            employee=employee, today=today_str())


@app.route("/employees/<int:employee_id>/deactivate", methods=["POST"])
def employee_deactivate(employee_id):
    ok, msg = emp.deactivate_employee(employee_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("employees"))


@app.route("/employees/<int:employee_id>/reactivate", methods=["POST"])
def employee_reactivate(employee_id):
    ok, msg = emp.reactivate_employee(employee_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("employees"))


@app.route("/employees/<int:employee_id>/delete", methods=["POST"])
def employee_delete(employee_id):
    ok, msg = emp.delete_employee(employee_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("employees"))


@app.route("/employees/<int:employee_id>/summary")
def employee_summary(employee_id):
    year = int(request.args.get("year", cur_year_month()[0]))
    month = int(request.args.get("month", cur_year_month()[1]))
    rec.generate_schedule_for_month_if_within_window(year, month)  # only auto-fills current/next month

    data = rp.employee_hours_breakdown(employee_id, year, month)
    if not data:
        flash("Employee not found.", "error")
        return redirect(url_for("employees"))

    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year
    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year

    return render_template("employee_summary.html", active="employees", data=data,
                            prev_year=prev_year, prev_month=prev_month,
                            next_year=next_year, next_month=next_month)


@app.route("/employees/<int:employee_id>/calendar")
def employee_calendar(employee_id):
    year = int(request.args.get("year", cur_year_month()[0]))
    month = int(request.args.get("month", cur_year_month()[1]))
    rec.generate_schedule_for_month_if_within_window(year, month)

    employee = emp.get_employee(employee_id)
    if not employee:
        flash("Employee not found.", "error")
        return redirect(url_for("employees"))

    weeks = rp.employee_monthly_calendar_grid(employee_id, year, month)

    # Overtime records live in a separate table from the schedule, but
    # showing them on the calendar too makes it a complete picture of a
    # day at a glance. This is a live, read-only merge each time the page
    # is viewed — deleting an OT record disappears from here automatically
    # on the next view, no separate cleanup needed.
    ot_by_date = {}
    for o in ot.list_overtime(employee_id=employee_id, year=year, month=month):
        ot_by_date.setdefault(o["ot_date"], []).append(o)
    for week in weeks:
        for day in week:
            if day is not None:
                day["ot_entries"] = ot_by_date.get(day["date"], [])

    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year
    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year

    return render_template("employee_calendar.html", active="employees",
                            employee=employee, weeks=weeks,
                            month_label=rp.month_name(year, month), today=today_str(),
                            prev_year=prev_year, prev_month=prev_month,
                            next_year=next_year, next_month=next_month)


# =============================================================== shifts =

@app.route("/shifts", methods=["GET", "POST"])
def shifts():
    if request.method == "POST":
        ok, msg = sh.add_shift_type(
            request.form["name"].strip(),
            request.form["start_time"],
            request.form["end_time"],
        )
        flash(msg, "success" if ok else "error")
        return redirect(url_for("shifts"))
    return render_template("shifts.html", active="shifts", shift_types=sh.list_shift_types())


@app.route("/shifts/<int:shift_type_id>/edit", methods=["POST"])
def shift_edit(shift_type_id):
    ok, msg = sh.update_shift_type(
        shift_type_id,
        name=request.form["name"].strip(),
        start_time=request.form["start_time"],
        end_time=request.form["end_time"],
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("shifts"))


@app.route("/shifts/<int:shift_type_id>/delete", methods=["POST"])
def shift_delete(shift_type_id):
    ok, msg = sh.delete_shift_type(shift_type_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("shifts"))


# ============================================================= schedule =

@app.route("/schedule")
def schedule_month():
    year = int(request.args.get("year", cur_year_month()[0]))
    month = int(request.args.get("month", cur_year_month()[1]))
    rec.generate_schedule_for_month_if_within_window(year, month)  # only auto-fills current/next month
    schedule_by_date = sc.get_monthly_schedule(year, month)

    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(None)
                continue
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            row.append({"day": day, "date": date_str,
                        "entries": schedule_by_date.get(date_str, [])})
        weeks.append(row)

    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year
    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year

    return render_template(
        "schedule.html", active="schedule", weeks=weeks,
        month_name=rp.month_name(year, month), year=year, month=month,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        today=today_str(),
    )


@app.route("/schedule/day/<date>")
def schedule_day(date):
    entries = sc.get_schedule_for_date(date)
    return render_template("schedule_day.html", active="schedule", date=date,
                            entries=entries, employees=emp.list_employees(status="Active"),
                            shift_types=sh.list_shift_types(),
                            employees_options=employee_search_options())


@app.route("/schedule/assign", methods=["POST"])
def schedule_assign():
    date = request.form["work_date"]
    ok, msg = sc.assign_shift(
        employee_id=int(request.form["employee_id"]),
        shift_type_id=int(request.form["shift_type_id"]),
        work_date=date,
        notes=request.form.get("notes", "").strip(),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("schedule_day", date=date))


@app.route("/schedule/<int:schedule_id>/status", methods=["POST"])
def schedule_status(schedule_id):
    status = request.form["status"]
    reason = request.form.get("reason", "Sick")
    ok, msg = sc.set_status_with_sync(schedule_id, status, reason=reason)
    flash(msg, "success" if ok else "error")
    return redirect(request.form.get("next") or url_for("schedule_month"))


@app.route("/schedule/<int:schedule_id>/delete", methods=["POST"])
def schedule_delete(schedule_id):
    ok, msg = sc.remove_schedule_entry(schedule_id)
    flash(msg, "success" if ok else "error")
    return redirect(request.form.get("next") or url_for("schedule_month"))


# ================================================== recurring patterns =

@app.route("/patterns")
def patterns():
    employee_id = request.args.get("employee_id")
    employee_id = int(employee_id) if employee_id and employee_id.isdigit() else None
    patterns = rec.list_patterns()
    if employee_id:
        patterns = [p for p in patterns if p["employee_id"] == employee_id]
    selected_employee = emp.get_employee(employee_id) if employee_id else None
    return render_template("patterns.html", active="schedule",
                            patterns=patterns,
                            employees=emp.list_employees(status="Active"),
                            employees_options=employee_search_options(),
                            shift_types=sh.list_shift_types(),
                            today=today_str(),
                            weekday_names=rec.WEEKDAY_NAMES,
                            employee_id=employee_id,
                            employee_filter_label=(
                                f"{selected_employee['first_name']} {selected_employee['last_name']} ({selected_employee['employee_code']})"
                                if selected_employee else ""
                            ))


@app.route("/patterns/new", methods=["POST"])
def pattern_new():
    end_date = request.form.get("effective_end", "").strip() or None
    ok, msg = rec.add_pattern(
        employee_id=int(request.form["employee_id"]),
        shift_type_id=int(request.form["shift_type_id"]),
        weekday=int(request.form["weekday"]),
        effective_start=request.form["effective_start"],
        effective_end=end_date,
        frequency=request.form.get("frequency", "weekly"),
        biweekly_week=int(request.form.get("biweekly_week", 1)),
        notes=request.form.get("notes", "").strip(),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("patterns"))


@app.route("/patterns/generate", methods=["POST"])
def pattern_generate():
    """Explicit, deliberate generation for a specific month — unlike the
    automatic per-page generation elsewhere, this isn't restricted to the
    current/next month, since the manager asked for this month by name."""
    year = int(request.form["year"])
    month = int(request.form["month"])
    created = rec.generate_schedule_for_month(year, month)
    flash(f"Generated {created} shift(s) for {rp.month_name(year, month)} from active patterns.", "success")
    return redirect(url_for("patterns"))


@app.route("/patterns/<int:pattern_id>/deactivate", methods=["POST"])
def pattern_deactivate(pattern_id):
    ok, msg = rec.deactivate_pattern(pattern_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("patterns"))


@app.route("/patterns/<int:pattern_id>/delete", methods=["POST"])
def pattern_delete(pattern_id):
    ok, msg = rec.delete_pattern(pattern_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("patterns"))


@app.route("/patterns/remove-employee", methods=["POST"])
def pattern_remove_employee():
    employee_id_raw = request.form.get("employee_id", "").strip()
    if not employee_id_raw or not employee_id_raw.isdigit():
        flash("Select an employee before removing pattern shifts.", "error")
        return redirect(url_for("patterns"))

    employee_id = int(employee_id_raw)
    removed = rec.remove_employee_pattern_schedule(employee_id)
    flash(
        f"Removed {removed['generated_shifts_removed']} pattern-generated shift(s) and "
        f"{removed['patterns_deleted']} recurring pattern(s) for that employee.",
        "success",
    )
    return redirect(url_for("patterns"))


# ============================================================= absences =

@app.route("/absences")
def absences():
    year = request.args.get("year")
    month = request.args.get("month")
    employee_id = request.args.get("employee_id")
    year = int(year) if year else None
    month = int(month) if month else None
    employee_id = int(employee_id) if employee_id and employee_id.isdigit() else None
    rows = ab.list_absences(employee_id=employee_id, year=year, month=month)
    summary = ab.absence_summary_by_employee(year, month)
    if employee_id:
        summary = [s for s in summary if s["id"] == employee_id]
    selected_employee = emp.get_employee(employee_id) if employee_id else None
    return render_template("absences.html", active="absences", absences=rows,
                            summary=summary, year=year, month=month,
                            employees=emp.list_employees(status="Active"),
                            employees_options=employee_search_options(),
                            employee_id=employee_id,
                            employee_filter_label=(
                                f"{selected_employee['first_name']} {selected_employee['last_name']} ({selected_employee['employee_code']})"
                                if selected_employee else ""
                            ))


@app.route("/absences/new", methods=["POST"])
def absence_new():
    schedule_id = request.form.get("schedule_id") or None
    covered_id = request.form.get("covered_by_employee_id") or None
    ok, msg = ab.record_absence(
        employee_id=int(request.form["employee_id"]),
        absence_date=request.form["absence_date"],
        reason=request.form.get("reason", "Sick"),
        schedule_id=int(schedule_id) if schedule_id else None,
        covered_by_employee_id=int(covered_id) if covered_id else None,
        notes=request.form.get("notes", "").strip(),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("absences"))


@app.route("/absences/<int:absence_id>/cover", methods=["POST"])
def absence_cover(absence_id):
    ok, msg = ab.set_coverage(absence_id, int(request.form["covered_by_employee_id"]))
    flash(msg, "success" if ok else "error")
    return redirect(url_for("absences"))

@app.route("/absences/<int:absence_id>/edit", methods=["GET", "POST"])
def absence_edit(absence_id):
    absence = ab.get_absence(absence_id)
    if not absence:
        flash("Absence record not found.", "error")
        return redirect(url_for("absences"))

    if request.method == "POST":
        covered_id = request.form.get("covered_by_employee_id") or None
        ok, msg = ab.update_absence(
            absence_id,
            employee_id=int(request.form["employee_id"]),
            absence_date=request.form["absence_date"],
            reason=request.form.get("reason", "Sick"),
            covered_by_employee_id=int(covered_id) if covered_id else None,
            notes=request.form.get("notes", "").strip(),
        )
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("absences"))
        absence = ab.get_absence(absence_id)  # re-fetch in case of partial failure

    return render_template("absence_edit.html", active="absences", absence=absence,
                            employees_options=employee_search_options())


@app.route("/absences/<int:absence_id>/delete", methods=["POST"])
def absence_delete(absence_id):
    ok, msg = ab.delete_absence(absence_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("absences"))


# ============================================================= overtime =

@app.route("/overtime")
def overtime():
    year = request.args.get("year")
    month = request.args.get("month")
    employee_id = request.args.get("employee_id")
    year = int(year) if year else None
    month = int(month) if month else None
    employee_id = int(employee_id) if employee_id and employee_id.isdigit() else None
    rows = ot.list_overtime(employee_id=employee_id, year=year, month=month)
    summary = ot.overtime_summary_by_employee(year, month)
    if employee_id:
        summary = [s for s in summary if s["id"] == employee_id]
    selected_employee = emp.get_employee(employee_id) if employee_id else None
    return render_template("overtime.html", active="overtime", overtime=rows,
                            summary=summary, year=year, month=month,
                            employees=emp.list_employees(status="Active"),
                            employees_options=employee_search_options(),
                            today=today_str(),
                            employee_id=employee_id,
                            employee_filter_label=(
                                f"{selected_employee['first_name']} {selected_employee['last_name']} ({selected_employee['employee_code']})"
                                if selected_employee else ""
                            ))


@app.route("/overtime/new", methods=["POST"])
def overtime_new():
    ok, msg = ot.record_overtime(
        employee_id=int(request.form["employee_id"]),
        ot_date=request.form["ot_date"],
        hours=float(request.form["hours"]),
        reason=request.form.get("reason", "").strip(),
        approved_by=request.form.get("approved_by", "").strip(),
        notes=request.form.get("notes", "").strip(),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("overtime"))


@app.route("/overtime/<int:overtime_id>/edit", methods=["GET", "POST"])
def overtime_edit(overtime_id):
    record = ot.get_overtime(overtime_id)
    if not record:
        flash("Overtime record not found.", "error")
        return redirect(url_for("overtime"))

    if request.method == "POST":
        ok, msg = ot.update_overtime(
            overtime_id,
            employee_id=int(request.form["employee_id"]),
            ot_date=request.form["ot_date"],
            hours=float(request.form["hours"]),
            reason=request.form.get("reason", "").strip(),
            approved_by=request.form.get("approved_by", "").strip(),
            notes=request.form.get("notes", "").strip(),
        )
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("overtime"))
        record = ot.get_overtime(overtime_id)

    return render_template("overtime_edit.html", active="overtime", record=record,
                            employees_options=employee_search_options())


@app.route("/overtime/<int:overtime_id>/delete", methods=["POST"])
def overtime_delete(overtime_id):
    ok, msg = ot.delete_overtime(overtime_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("overtime"))


# ============================================================== reports =

@app.route("/reports")
def reports():
    year = int(request.args.get("year", cur_year_month()[0]))
    month = int(request.args.get("month", cur_year_month()[1]))
    employee_id = request.args.get("employee_id")
    employee_id = int(employee_id) if employee_id and employee_id.isdigit() else None
    rec.generate_schedule_for_month_if_within_window(year, month)
    employees = emp.list_employees(status="Active")
    if employee_id:
        employees = [e for e in employees if e["id"] == employee_id]
    summaries = [rp.employee_hours_breakdown(e["id"], year, month)
                 for e in employees]
    total_annual_hours = round(sum((s["expected_hours_annually"] or 0) for s in summaries if s), 2)
    total_monthly_hours = round(sum((s["expected_hours_monthly"] or 0) for s in summaries if s), 2)
    selected_employee = emp.get_employee(employee_id) if employee_id else None
    return render_template("reports.html", active="reports", summaries=summaries,
                            year=year, month=month, month_name=rp.month_name(year, month),
                            employees_options=employee_search_options(),
                            employee_id=employee_id,
                            total_annual_hours=total_annual_hours,
                            total_monthly_hours= total_monthly_hours,
                            employee_filter_label=(
                                f"{selected_employee['first_name']} {selected_employee['last_name']} ({selected_employee['employee_code']})"
                                if selected_employee else ""
                            ))


@app.route("/reports/export")
def reports_export():
    year = int(request.args.get("year", cur_year_month()[0]))
    month = int(request.args.get("month", cur_year_month()[1]))
    employee_id = request.args.get("employee_id")
    employee_id = int(employee_id) if employee_id and employee_id.isdigit() else None
    filename = f"employee-hours-{year:04d}-{month:02d}.xlsx"
    out_path = os.path.join(tempfile.gettempdir(), filename)
    exp.export_monthly_summary_to_excel(year, month, out_path, status="Active", employee_id=employee_id)
    return send_file(out_path, as_attachment=True, download_name=filename,
                      mimetype="application/vnd/openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    url = "http://127.0.0.1:5000"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(debug=False, port=5000, use_reloader=False)
