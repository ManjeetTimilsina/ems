"""
absences.py
Record sick / other absences, and track who covered the shift (if anyone).
Recording an absence automatically marks the linked schedule entry as
'Absent' (or 'Covered' if a covering employee is supplied), and — when
possible — auto-links to the absent employee's own scheduled shift for
that date so hours can be computed without anyone needing to look up a
schedule ID.

Coverage is also reflected as an actual schedule entry for the covering
employee (tagged in its notes), so it shows up on their own calendar like
any other shift — see _sync_coverage_schedule_row(). Adding, changing, or
removing coverage (via set_coverage() or by deleting the absence) keeps
that entry in sync automatically. Deleting an absence also reverts the
originally-absent employee's schedule entry back to 'Scheduled', so the
Absent/Covered mark doesn't linger after the record is gone.

Whether a covered shift counts as the covering employee's regular hours
or overtime is decided in reports.py by looking at their combined
daily/biweekly hours for the period, not here.
"""

from ems.database import get_connection

COVERAGE_NOTE_TAG = "Covering shift for a colleague"


def _sync_coverage_schedule_row(schedule_id, old_covered_by, new_covered_by):
    """Move the auto-generated "covering" schedule entry from
    old_covered_by to new_covered_by for the shift referenced by
    schedule_id, so a covering employee's calendar actually shows the
    shift they picked up. Safe to call with old/new equal or None.

    If the covering employee already has their own entry for that exact
    date/shift type (an unusual double-booking edge case), it's left
    untouched rather than overwritten — it already represents them
    working, and this avoids any ambiguity about what to restore if the
    coverage is later removed.
    """
    if schedule_id is None or old_covered_by == new_covered_by:
        return
    conn = get_connection()
    try:
        row = conn.execute("SELECT shift_type_id, work_date FROM schedule WHERE id = ?",
                            (schedule_id,)).fetchone()
        if not row:
            return
        shift_type_id, work_date = row["shift_type_id"], row["work_date"]

        if old_covered_by:
            conn.execute("""
                DELETE FROM schedule
                WHERE employee_id = ? AND work_date = ? AND shift_type_id = ? AND notes = ?
            """, (old_covered_by, work_date, shift_type_id, COVERAGE_NOTE_TAG))

        if new_covered_by:
            existing = conn.execute("""
                SELECT id FROM schedule WHERE employee_id = ? AND work_date = ? AND shift_type_id = ?
            """, (new_covered_by, work_date, shift_type_id)).fetchone()
            if not existing:
                conn.execute("""
                    INSERT INTO schedule (employee_id, shift_type_id, work_date, status, notes)
                    VALUES (?, ?, ?, 'Worked', ?)
                """, (new_covered_by, shift_type_id, work_date, COVERAGE_NOTE_TAG))
        conn.commit()
    finally:
        conn.close()


def record_absence(employee_id, absence_date, reason="Sick", schedule_id=None,
                    covered_by_employee_id=None, notes=""):
    conn = get_connection()
    try:
        # Auto-link to the employee's own scheduled shift that day if the
        # caller didn't specify one, so hours (and coverage credit for
        # whoever covers it) compute correctly without requiring anyone
        # to look up and enter a schedule ID by hand.
        if schedule_id is None:
            candidate = conn.execute("""
                SELECT id FROM schedule WHERE employee_id = ? AND work_date = ?
                ORDER BY id LIMIT 1
            """, (employee_id, absence_date)).fetchone()
            if candidate:
                schedule_id = candidate["id"]

        conn.execute("""
            INSERT INTO absences
                (employee_id, absence_date, reason, schedule_id, covered_by_employee_id, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (employee_id, absence_date, reason, schedule_id, covered_by_employee_id, notes))

        # Reflect the absence on the linked schedule entry, if provided
        if schedule_id is not None:
            new_status = "Covered" if covered_by_employee_id else "Absent"
            conn.execute("UPDATE schedule SET status = ? WHERE id = ?",
                         (new_status, schedule_id))

        conn.commit()
    except Exception as e:
        return False, f"Error recording absence: {e}"
    finally:
        conn.close()

    if covered_by_employee_id:
        _sync_coverage_schedule_row(schedule_id, None, covered_by_employee_id)
    return True, "Absence recorded."


def set_coverage(absence_id, covered_by_employee_id):
    """Attach or change who covered an already-recorded absence."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT schedule_id, covered_by_employee_id FROM absences WHERE id = ?",
                            (absence_id,)).fetchone()
        if not row:
            return False, "Absence record not found."
        old_covered_by = row["covered_by_employee_id"]
        schedule_id = row["schedule_id"]

        conn.execute("UPDATE absences SET covered_by_employee_id = ? WHERE id = ?",
                     (covered_by_employee_id, absence_id))
        if schedule_id is not None:
            new_status = "Covered" if covered_by_employee_id else "Absent"
            conn.execute("UPDATE schedule SET status = ? WHERE id = ?",
                         (new_status, schedule_id))
        conn.commit()
    except Exception as e:
        return False, f"Error setting coverage: {e}"
    finally:
        conn.close()

    _sync_coverage_schedule_row(schedule_id, old_covered_by, covered_by_employee_id)
    return True, "Coverage recorded."


def update_absence(absence_id, employee_id, absence_date, reason, covered_by_employee_id, notes):
    """Edit an existing absence record's core fields. If the employee or
    date changes, the old linked schedule entry (if any) reverts to
    'Scheduled' and a new one is looked up for the new employee/date —
    the same auto-link behavior as recording a fresh absence. Coverage
    changes are handled the same way as set_coverage(), keeping the
    covering employee's own calendar entry in sync either way."""
    conn = get_connection()
    old = conn.execute("SELECT * FROM absences WHERE id = ?", (absence_id,)).fetchone()
    if not old:
        conn.close()
        return False, "Absence record not found."
    old = dict(old)
    conn.close()

    employee_or_date_changed = (
        employee_id != old["employee_id"] or absence_date != old["absence_date"]
    )

    schedule_id = old["schedule_id"]
    old_covered_by = old["covered_by_employee_id"]

    if employee_or_date_changed:
        # Revert the old linked shift and remove any coverage entry tied
        # to it — this absence now belongs to a different employee/date.
        if schedule_id is not None:
            conn2 = get_connection()
            try:
                conn2.execute("UPDATE schedule SET status = 'Scheduled' WHERE id = ?", (schedule_id,))
                conn2.commit()
            finally:
                conn2.close()
        if old_covered_by:
            _sync_coverage_schedule_row(schedule_id, old_covered_by, None)
            old_covered_by = None  # already cleaned up; treat as fresh below

        # Auto-link to the new employee's own scheduled shift that date,
        # same as record_absence() does for a brand new absence.
        conn3 = get_connection()
        candidate = conn3.execute("""
            SELECT id FROM schedule WHERE employee_id = ? AND work_date = ?
            ORDER BY id LIMIT 1
        """, (employee_id, absence_date)).fetchone()
        schedule_id = candidate["id"] if candidate else None
        conn3.close()

    conn = get_connection()
    try:
        conn.execute("""
            UPDATE absences
            SET employee_id = ?, absence_date = ?, reason = ?, schedule_id = ?,
                covered_by_employee_id = ?, notes = ?
            WHERE id = ?
        """, (employee_id, absence_date, reason, schedule_id, covered_by_employee_id, notes, absence_id))

        if schedule_id is not None:
            new_status = "Covered" if covered_by_employee_id else "Absent"
            conn.execute("UPDATE schedule SET status = ? WHERE id = ?", (new_status, schedule_id))
        conn.commit()
    except Exception as e:
        return False, f"Error updating absence: {e}"
    finally:
        conn.close()

    _sync_coverage_schedule_row(schedule_id, old_covered_by, covered_by_employee_id)
    return True, "Absence updated."


def delete_absence(absence_id):
    """Delete an absence record. If it was linked to a schedule entry,
    that entry reverts to 'Scheduled' (the Absent/Covered mark doesn't
    linger). If it had a covering employee, their synthetic coverage
    entry is removed from their own calendar too."""
    conn = get_connection()
    row = conn.execute("SELECT schedule_id, covered_by_employee_id FROM absences WHERE id = ?",
                        (absence_id,)).fetchone()
    try:
        cur = conn.execute("DELETE FROM absences WHERE id = ?", (absence_id,))
        conn.commit()
        if cur.rowcount == 0:
            return False, "Absence record not found."
    except Exception as e:
        return False, f"Error deleting absence: {e}"
    finally:
        conn.close()

    if row and row["schedule_id"] is not None:
        conn2 = get_connection()
        try:
            conn2.execute("UPDATE schedule SET status = 'Scheduled' WHERE id = ?", (row["schedule_id"],))
            conn2.commit()
        finally:
            conn2.close()

    if row and row["covered_by_employee_id"]:
        _sync_coverage_schedule_row(row["schedule_id"], row["covered_by_employee_id"], None)

    return True, "Absence record deleted."


def get_absence(absence_id):
    """A single absence record with both raw fields (employee_id,
    covered_by_employee_id — needed to pre-fill an edit form) and the
    joined display fields used elsewhere (employee name, etc.)."""
    conn = get_connection()
    row = conn.execute("""
        SELECT a.*, e.employee_code, e.first_name AS emp_first, e.last_name AS emp_last,
               c.employee_code AS covered_code, c.first_name AS cov_first, c.last_name AS cov_last
        FROM absences a
        JOIN employees e ON e.id = a.employee_id
        LEFT JOIN employees c ON c.id = a.covered_by_employee_id
        WHERE a.id = ?
    """, (absence_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_absences(employee_id=None, year=None, month=None, reason=None):
    conn = get_connection()
    query = """
        SELECT a.id, a.absence_date, a.reason, a.notes, a.schedule_id,
               e.employee_code, e.first_name AS emp_first, e.last_name AS emp_last,
               c.employee_code AS covered_code, c.first_name AS cov_first, c.last_name AS cov_last,
               st.hours AS linked_shift_hours
        FROM absences a
        JOIN employees e ON e.id = a.employee_id
        LEFT JOIN employees c ON c.id = a.covered_by_employee_id
        LEFT JOIN schedule s ON s.id = a.schedule_id
        LEFT JOIN shift_types st ON st.id = s.shift_type_id
        WHERE 1=1
    """
    params = []
    if employee_id:
        query += " AND a.employee_id = ?"
        params.append(employee_id)
    if reason:
        query += " AND a.reason = ?"
        params.append(reason)
    if year and month:
        query += " AND strftime('%Y', a.absence_date) = ? AND strftime('%m', a.absence_date) = ?"
        params.extend([f"{year:04d}", f"{month:02d}"])
    query += " ORDER BY a.absence_date DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def coverage_hours_for_employee(employee_id, year=None, month=None):
    """Total hours this employee worked covering other people's absences —
    credited toward their own hours total even though it wasn't their
    originally scheduled shift. Whether these end up counted as regular
    or overtime hours is decided in reports.py by looking at combined
    daily/weekly totals, not here."""
    conn = get_connection()
    query = """
        SELECT st.hours AS linked_hours
        FROM absences a
        LEFT JOIN schedule s ON s.id = a.schedule_id
        LEFT JOIN shift_types st ON st.id = s.shift_type_id
        WHERE a.covered_by_employee_id = ?
    """
    params = [employee_id]
    if year and month:
        query += " AND strftime('%Y', a.absence_date) = ? AND strftime('%m', a.absence_date) = ?"
        params.extend([f"{year:04d}", f"{month:02d}"])
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return round(sum((r["linked_hours"] or 0) for r in rows), 2)


def coverage_hours_by_date_for_employee(employee_id, year=None, month=None):
    """Same as coverage_hours_for_employee, but broken out per date (the
    date of the shift they covered) — used to fold coverage into the
    daily/weekly overtime calculation accurately, since it matters which
    specific day those hours landed on."""
    conn = get_connection()
    query = """
        SELECT a.absence_date AS work_date, st.hours AS hours
        FROM absences a
        LEFT JOIN schedule s ON s.id = a.schedule_id
        LEFT JOIN shift_types st ON st.id = s.shift_type_id
        WHERE a.covered_by_employee_id = ?
    """
    params = [employee_id]
    if year and month:
        query += " AND strftime('%Y', a.absence_date) = ? AND strftime('%m', a.absence_date) = ?"
        params.extend([f"{year:04d}", f"{month:02d}"])
    rows = conn.execute(query, params).fetchall()
    conn.close()

    by_date = {}
    for r in rows:
        if r["hours"] is None:
            continue
        by_date[r["work_date"]] = by_date.get(r["work_date"], 0.0) + r["hours"]
    return by_date


def absence_summary_by_employee(year=None, month=None):
    """Count of absences per employee, optionally filtered to a month."""
    conn = get_connection()
    query = """
        SELECT e.id, e.employee_code, e.first_name, e.last_name, COUNT(a.id) AS absence_count
        FROM employees e
        LEFT JOIN absences a ON a.employee_id = e.id
    """
    params = []
    if year and month:
        query += " AND strftime('%Y', a.absence_date) = ? AND strftime('%m', a.absence_date) = ?"
        params.extend([f"{year:04d}", f"{month:02d}"])
    query += " GROUP BY e.id ORDER BY absence_count DESC, e.last_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
