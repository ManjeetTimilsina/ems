"""
schedule.py
Assign employees to shifts on specific dates and build monthly schedules.
"""

import calendar
from ems.database import get_connection
from ems import absences as ab_mod


def assign_shift(employee_id, shift_type_id, work_date, status="Scheduled", notes=""):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO schedule (employee_id, shift_type_id, work_date, status, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (employee_id, shift_type_id, work_date, status, notes))
        conn.commit()
        return True, "Shift assigned."
    except Exception as e:
        return False, f"Error assigning shift (duplicate or invalid IDs?): {e}"
    finally:
        conn.close()


def update_schedule_status(schedule_id, status, notes=None):
    conn = get_connection()
    try:
        if notes is not None:
            conn.execute("UPDATE schedule SET status = ?, notes = ? WHERE id = ?",
                         (status, notes, schedule_id))
        else:
            conn.execute("UPDATE schedule SET status = ? WHERE id = ?", (status, schedule_id))
        conn.commit()
        return True, "Schedule entry updated."
    except Exception as e:
        return False, f"Error updating schedule entry: {e}"
    finally:
        conn.close()


def set_status_with_sync(schedule_id, new_status, reason="Sick", covered_by_employee_id=None, notes=""):
    """Change a schedule entry's status while keeping the absences table in
    sync, so hours (sick/personal/vacation/etc.) are always counted
    correctly no matter which control was used to mark it — the quick
    status dropdown/buttons, or the full "Record an Absence" form.

    - Setting status to Absent or Covered creates a matching absence
      record if one doesn't already exist yet (or updates it if it does),
      so leave hours are picked up automatically.
    - Setting status back to Scheduled or Worked removes any absence
      record tied to this shift, so it stops being counted as leave.
    """
    conn = get_connection()
    row = conn.execute("SELECT employee_id, work_date FROM schedule WHERE id = ?",
                        (schedule_id,)).fetchone()
    if not row:
        conn.close()
        return False, "Schedule entry not found."
    employee_id, work_date = row["employee_id"], row["work_date"]

    existing = conn.execute("SELECT id FROM absences WHERE schedule_id = ?",
                             (schedule_id,)).fetchone()
    conn.close()

    if new_status in ("Absent", "Covered"):
        if existing:
            conn2 = get_connection()
            try:
                conn2.execute(
                    "UPDATE absences SET reason = ?, covered_by_employee_id = ?, notes = ? WHERE id = ?",
                    (reason, covered_by_employee_id, notes, existing["id"]))
                conn2.commit()
            finally:
                conn2.close()
            sched_status = "Covered" if covered_by_employee_id else "Absent"
            return update_schedule_status(schedule_id, sched_status)
        else:
            return ab_mod.record_absence(employee_id, work_date, reason=reason,
                                          schedule_id=schedule_id,
                                          covered_by_employee_id=covered_by_employee_id,
                                          notes=notes)
    else:
        # Back to Scheduled/Worked: this shift is no longer a leave day,
        # so remove any absence record that had been tied to it.
        if existing:
            ab_mod.delete_absence(existing["id"])
        return update_schedule_status(schedule_id, new_status, notes=notes or None)


def remove_schedule_entry(schedule_id):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM schedule WHERE id = ?", (schedule_id,))
        conn.commit()
        if cur.rowcount == 0:
            return False, "Schedule entry not found."
        return True, "Schedule entry removed."
    except Exception as e:
        return False, f"Error removing schedule entry: {e}"
    finally:
        conn.close()


def get_schedule_for_date(work_date):
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.id, s.employee_id, s.shift_type_id, e.employee_code, e.first_name, e.last_name, e.department,
               st.name AS shift_name, st.start_time, st.end_time, st.hours,
               s.status, s.notes
        FROM schedule s
        JOIN employees e ON e.id = s.employee_id
        JOIN shift_types st ON st.id = s.shift_type_id
        WHERE s.work_date = ?
        ORDER BY st.start_time, e.last_name
    """, (work_date,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_schedule_for_employee_month(employee_id, year, month):
    conn = get_connection()
    start = f"{year:04d}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year:04d}-{month:02d}-{last_day:02d}"
    rows = conn.execute("""
        SELECT s.id, s.work_date, st.name AS shift_name, st.start_time,
               st.end_time, st.hours, s.status, s.notes
        FROM schedule s
        JOIN shift_types st ON st.id = s.shift_type_id
        WHERE s.employee_id = ? AND s.work_date BETWEEN ? AND ?
        ORDER BY s.work_date
    """, (employee_id, start, end)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_schedule(year, month):
    """Return the full schedule for every employee for a given month,
    grouped by date."""
    conn = get_connection()
    start = f"{year:04d}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year:04d}-{month:02d}-{last_day:02d}"
    rows = conn.execute("""
        SELECT s.id, s.employee_id, s.shift_type_id, s.work_date, e.employee_code, e.first_name, e.last_name,
               st.name AS shift_name, st.start_time, st.end_time, st.hours,
               s.status
        FROM schedule s
        JOIN employees e ON e.id = s.employee_id
        JOIN shift_types st ON st.id = s.shift_type_id
        WHERE s.work_date BETWEEN ? AND ?
        ORDER BY s.work_date, st.start_time, e.last_name
    """, (start, end)).fetchall()
    conn.close()

    schedule_by_date = {}
    for r in rows:
        schedule_by_date.setdefault(r["work_date"], []).append(dict(r))
    return schedule_by_date


def total_scheduled_hours(employee_id, year, month):
    """Sum of scheduled (non-absent) shift hours for an employee in a month."""
    entries = get_schedule_for_employee_month(employee_id, year, month)
    return round(sum(e["hours"] for e in entries if e["status"] != "Absent"), 2)
