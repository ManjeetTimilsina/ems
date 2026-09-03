"""
reports.py
Higher-level reports combining employees, schedule, absences and overtime.
"""

import calendar
import datetime as dt
from ems.database import get_connection
from ems import employees as emp_mod
from ems import schedule as sched_mod
from ems import absences as abs_mod
from ems import overtime as ot_mod



# Overtime is auto-detected from actual hours worked (own shifts + any
# coverage), the way many labor rules work: hours beyond the daily
# threshold on a single day become daily OT; whatever's left over (the
# "base" hours) are then checked against the weekly threshold, and any
# excess becomes weekly OT. It doesn't matter whether the hours came from
# an employee's own shift or from covering a colleague — payroll doesn't
# care whose shift it was, only how many hours were actually worked.
# Adjust these to match your jurisdiction/company policy.

OT_BIWEEKLY_THRESHOLD_HOURS = 80.0

PAYROLL_ANCHOR_DATE = dt.date(2026, 8, 1)

def calculate_paid_hours(employee, scheduled_hours):


    position = (employee.get("position") or "").strip().lower()
    schedule_round = round(scheduled_hours, 2)

    if "nurse" in position and schedule_round == 8.0:
        return 7.75
    elif "security" in position and schedule_round == 12.0:
        return 11.0
    elif schedule_round == 8.0:
        return 7.5

    return scheduled_hours

def get_standard_monthly_hours(employee):
    """Returns the baseline full-time hours for a month based on the employee's role."""
    position = (employee.get("position") or "").strip().lower()
    if "nurse" in position:
        return 7.75 * 20  # 155.0 hours
    elif "security" in position:
        return 11.0 * 14  # 154.0 hours
    return 7.5 * 20       # 150.0 hours


def _daily_totals_for_employee(employee_id, year, month):
    """{date_str: hours_worked_that_day} from this employee's own
    Worked/Scheduled shifts for one month. Hours picked up covering a
    colleague are included automatically too — coverage is reflected as
    a real schedule entry for the covering employee (see
    absences._sync_coverage_schedule_row), so it's already part of the
    normal scan below rather than needing to be added separately here
    (which would double-count it).

    A 'Scheduled' shift only counts as worked once its date has actually
    passed (today or earlier) — a future Scheduled shift is still just a
    plan, not hours worked yet. 'Worked' entries always count regardless
    of date, since that status is an explicit confirmation.
    """
    employee = emp_mod.get_employee(employee_id)
    if not employee:
        return {}

    today_str = dt.date.today().strftime("%Y-%m-%d")
    entries = sched_mod.get_schedule_for_employee_month(employee_id, year, month)
    totals = {}
    for e in entries:
        if e["status"] == "Worked" or (e["status"] == "Scheduled" and e["work_date"] <= today_str):
            date_str = e["work_date"]
            paid_hours = calculate_paid_hours(employee, e["hours"])

            if date_str not in totals:
                totals[date_str] = {"paid_hours": 0.0, "threshold": 8.0}

            totals[date_str]["paid_hours"] += paid_hours

            if round(e["hours"], 2) == 12.0:
                totals[date_str]["threshold"] = 12.0

    return totals


def _compute_auto_overtime(daily_totals,biweekly_threshold=OT_BIWEEKLY_THRESHOLD_HOURS):
    """Given {date_str: hours}, split into (regular_hours, auto_ot_hours)
    using daily-then-weekly thresholds.

    Note: weeks are grouped using only the dates present in daily_totals
    (i.e. within the requested month), so a week that spans a month
    boundary is evaluated using just the days that fall in this month —
    OT on a boundary week could be slightly understated for that reason.
    """
    daily_ot_total = 0.0
    base_by_biweek = {}
    for date_str, data in daily_totals.items():
        d = dt.datetime.strptime(date_str, "%Y-%m-%d").date()

        hours = data["paid_hours"]
        daily_threshold = data["threshold"]
        daily_ot = max(0.0, hours - daily_threshold)
        base = hours - daily_ot
        daily_ot_total += daily_ot

        days_since_anchor = (d - PAYROLL_ANCHOR_DATE).days

        biweek_key = days_since_anchor // 14

        base_by_biweek[biweek_key] = base_by_biweek.get(biweek_key, 0.0) + base


    biweekly_ot_total = 0.0
    base_total = 0.0
    for base_hours in base_by_biweek.values():
        base_total += base_hours
        if base_hours > biweekly_threshold:
            biweekly_ot_total += base_hours - biweekly_threshold

    regular_hours = base_total - biweekly_ot_total
    auto_ot_hours = daily_ot_total + biweekly_ot_total
    return round(regular_hours, 2), round(auto_ot_hours, 2), round(daily_ot_total, 2), round(biweekly_ot_total, 2)


def employee_monthly_summary(employee_id, year, month):
    """Combine scheduled hours, absences, OT and EFT-expected hours for one
    employee in a given month."""
    employee = emp_mod.get_employee(employee_id)
    if not employee:
        return None

    scheduled_hours = sched_mod.total_scheduled_hours(employee_id, year, month)
    absences = abs_mod.list_absences(employee_id=employee_id, year=year, month=month)
    ot_hours = ot_mod.total_overtime_hours(employee_id, year=year, month=month)
    base_working_hours = get_standard_monthly_hours(employee)
    expected_hours_monthly = round(base_working_hours* employee["eft"], 2)
    expected_hours_annually = round(expected_hours_monthly * 13, 2)

    return {
        "employee_code": employee["employee_code"],
        "name": f"{employee['first_name']} {employee['last_name']}",
        "eft": employee["eft"],
        "expected_hours_monthly": expected_hours_monthly,
        "expected_hours_annually": expected_hours_annually,
        "scheduled_hours": scheduled_hours,
        "hours_variance": round(scheduled_hours - expected_hours_monthly, 2),
        "absence_count": len(absences),
        "sick_count": len([a for a in absences if a["reason"] == "Sick"]),
        "overtime_hours": ot_hours,
    }


def all_employees_monthly_summary(year, month):
    result = []
    for e in emp_mod.list_employees(status="Active"):
        result.append(employee_monthly_summary(e["id"], year, month))
    return result


def employee_hours_breakdown(employee_id, year, month):
    """Full individual monthly report for one employee: hours worked
    (regular vs. auto-detected overtime), hours of sick/other leave
    (broken out by reason), manually-logged OT, and the employee's own
    day-by-day schedule for the month — everything needed for a "my
    hours this month" view. Automatically reflects whatever is in the
    schedule/absences/overtime tables for that month, so calling this
    after generate_schedule_for_month() gives an always-current picture
    without any manual recalculation.
    """
    employee = emp_mod.get_employee(employee_id)
    if not employee:
        return None

    entries = sched_mod.get_schedule_for_employee_month(employee_id, year, month)
    scheduled_hours = round(sum(e["hours"] for e in entries), 2)
    covered_away_hours = round(sum(
        calculate_paid_hours(employee, e["hours"]) for e in entries if e["status"] == "Covered"
    ), 2)
    absent_hours = round(sum(
        calculate_paid_hours(employee, e["hours"]) for e in entries if e["status"] == "Absent"
    ), 2)

    # Hours this employee spent covering someone else's shift — informational
    # detail. The actual worked-hours total below already includes these
    # hours via the real schedule entry created for the covering shift
    # (see absences._sync_coverage_schedule_row), not via this figure.
    coverage_hours = abs_mod.coverage_hours_for_employee(employee_id, year=year, month=month)
    coverage_given_hours = calculate_paid_hours(employee, coverage_hours)
    # Split actual hours worked (own shifts + coverage, both now part of
    # the same schedule scan) into regular vs. auto-detected overtime.
    daily_totals = _daily_totals_for_employee(employee_id, year, month)
    worked_hours, auto_ot_hours, daily_ot_hours, biweekly_ot_hours = _compute_auto_overtime(daily_totals)

    # Build a lookup of this employee's own schedule entries by date, used
    # as a fallback when an absence isn't linked to a specific schedule_id.
    entries_by_date = {}
    for e in entries:
        entries_by_date.setdefault(e["work_date"], []).append(e)

    absences = abs_mod.list_absences(employee_id=employee_id, year=year, month=month)
    leave_hours_by_reason = {"Sick": 0.0, "Personal": 0.0, "Vacation": 0.0, "Other": 0.0}
    unpaid_hours_total  = 0.0
    for a in absences:
        hours = a.get("linked_shift_hours")
        if hours is None:
            # Not linked to a specific schedule row — fall back to any
            # shift this employee had scheduled that same date.
            same_day = entries_by_date.get(a["absence_date"])
            hours = same_day[0]["hours"] if same_day else 0

        work_hours = calculate_paid_hours(employee, hours)
        reason = a["reason"]
        if reason == "Unpaid":
            unpaid_hours_total += work_hours

        else:
            paid_leave_hours = calculate_paid_hours(employee, hours)

            contain = reason if reason in leave_hours_by_reason else "Other"
            leave_hours_by_reason[contain] += paid_leave_hours

    for k in leave_hours_by_reason:
        leave_hours_by_reason[k] = round(leave_hours_by_reason[k], 2)
    total_paid_leave_hours = round(sum(leave_hours_by_reason.values()), 2)

    manual_overtime_hours = ot_mod.total_overtime_hours(employee_id, year=year, month=month)
    overtime_hours = round(manual_overtime_hours + auto_ot_hours, 2)
    base_working_hours = get_standard_monthly_hours(employee)
    expected_hours_monthly = round(base_working_hours* employee["eft"], 2)
    expected_hours_annually = round(expected_hours_monthly * 13, 2)
    total_paid_hours = round(worked_hours + overtime_hours + total_paid_leave_hours, 2)

    return {
        "employee": employee,
        "year": year,
        "month": month,
        "month_label": month_name(year, month),
        "expected_hours_monthly": expected_hours_monthly,
        "expected_hours_annually": expected_hours_annually,
        "scheduled_hours": scheduled_hours,
        "worked_hours": worked_hours,               # regular (non-OT) hours actually worked
        "covered_away_hours": covered_away_hours,    # shifts this employee was absent for, someone else covered
        "coverage_given_hours": coverage_given_hours,  # hours this employee worked covering others (info only)
        "absent_hours": absent_hours,                # hours marked Absent with no coverage
        "sick_hours": leave_hours_by_reason["Sick"],
        "personal_hours": leave_hours_by_reason["Personal"],
        "vacation_hours": leave_hours_by_reason["Vacation"],
        "other_leave_hours": leave_hours_by_reason["Other"],
        "unpaid_leave_hours": unpaid_hours_total,
        "total_leave_hours": total_paid_leave_hours,
        "manual_overtime_hours": manual_overtime_hours,  # from the Overtime page/table
        "auto_overtime_hours": auto_ot_hours,            # auto-detected from daily/weekly thresholds
        "auto_overtime_daily": daily_ot_hours,           # portion from exceeding the daily threshold
        "auto_overtime_biweekly": biweekly_ot_hours,         # portion from exceeding the weekly threshold
        "overtime_hours": overtime_hours,                # manual + auto, total
        "total_paid_hours": total_paid_hours,
        "absence_count": len(absences),
        "schedule_entries": entries,     # the individual month schedule itself
        "absences": absences,
    }


def month_name(year, month):
    return f"{calendar.month_name[month]} {year}"


def print_monthly_calendar(year, month):
    """Return a text calendar showing shift coverage counts per day (a
    quick way to see under/over-staffed days at a glance)."""
    schedule_by_date = sched_mod.get_monthly_schedule(year, month)
    cal = calendar.Calendar(firstweekday=0)
    lines = [f"\n{month_name(year, month)} - Staffing Overview", "=" * 40]
    for week in cal.monthdayscalendar(year, month):
        parts = []
        for day in week:
            if day == 0:
                parts.append("      ")
                continue
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            count = len(schedule_by_date.get(date_str, []))
            parts.append(f"{day:2d}({count:2d})")
        lines.append(" ".join(parts))
    lines.append("(day(number of shifts scheduled))")
    return "\n".join(lines)


def employee_monthly_calendar_grid(employee_id, year, month):
    """A week-by-week calendar grid (Mon-first) of one employee's schedule
    for a month — each cell is either None (padding outside the month) or
    {'day': int, 'date': str, 'entries': [schedule rows for that date]}.
    Used to render an actual calendar view rather than a flat list."""
    entries = sched_mod.get_schedule_for_employee_month(employee_id, year, month)
    by_date = {}
    for e in entries:
        by_date.setdefault(e["work_date"], []).append(e)

    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(None)
            else:
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                row.append({"day": day, "date": date_str, "entries": by_date.get(date_str, [])})
        weeks.append(row)
    return weeks
