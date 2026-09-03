"""
overtime.py
Record and report overtime (OT) hours worked by employees.
"""

from ems.database import get_connection


def record_overtime(employee_id, ot_date, hours, reason="", approved_by="", notes=""):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO overtime (employee_id, ot_date, hours, reason, approved_by, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (employee_id, ot_date, hours, reason, approved_by, notes))
        conn.commit()
        return True, "Overtime recorded."
    except Exception as e:
        return False, f"Error recording overtime: {e}"
    finally:
        conn.close()


def get_overtime(overtime_id):
    conn = get_connection()
    row = conn.execute("""
        SELECT o.id, o.employee_id, o.ot_date, o.hours, o.reason, o.approved_by, o.notes,
               e.employee_code, e.first_name, e.last_name
        FROM overtime o
        JOIN employees e ON e.id = o.employee_id
        WHERE o.id = ?
    """, (overtime_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_overtime(overtime_id, employee_id, ot_date, hours, reason="", approved_by="", notes=""):
    conn = get_connection()
    try:
        cur = conn.execute("""
            UPDATE overtime
            SET employee_id = ?, ot_date = ?, hours = ?, reason = ?, approved_by = ?, notes = ?
            WHERE id = ?
        """, (employee_id, ot_date, hours, reason, approved_by, notes, overtime_id))
        conn.commit()
        if cur.rowcount == 0:
            return False, "Overtime record not found."
        return True, "Overtime updated."
    except Exception as e:
        return False, f"Error updating overtime: {e}"
    finally:
        conn.close()


def delete_overtime(overtime_id):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM overtime WHERE id = ?", (overtime_id,))
        conn.commit()
        if cur.rowcount == 0:
            return False, "Overtime record not found."
        return True, "Overtime record deleted."
    except Exception as e:
        return False, f"Error deleting overtime record: {e}"
    finally:
        conn.close()


def list_overtime(employee_id=None, year=None, month=None):
    conn = get_connection()
    query = """
        SELECT o.id, o.ot_date, o.hours, o.reason, o.approved_by, o.notes,
               e.employee_code, e.first_name, e.last_name
        FROM overtime o
        JOIN employees e ON e.id = o.employee_id
        WHERE 1=1
    """
    params = []
    if employee_id:
        query += " AND o.employee_id = ?"
        params.append(employee_id)
    if year and month:
        query += " AND strftime('%Y', o.ot_date) = ? AND strftime('%m', o.ot_date) = ?"
        params.extend([f"{year:04d}", f"{month:02d}"])
    query += " ORDER BY o.ot_date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def total_overtime_hours(employee_id, year=None, month=None):
    entries = list_overtime(employee_id=employee_id, year=year, month=month)
    return round(sum(e["hours"] for e in entries), 2)


def overtime_summary_by_employee(year=None, month=None):
    conn = get_connection()
    query = """
        SELECT e.id, e.employee_code, e.first_name, e.last_name,
               COALESCE(SUM(o.hours), 0) AS total_ot_hours
        FROM employees e
        LEFT JOIN overtime o ON o.employee_id = e.id
    """
    params = []
    if year and month:
        query += " AND strftime('%Y', o.ot_date) = ? AND strftime('%m', o.ot_date) = ?"
        params.extend([f"{year:04d}", f"{month:02d}"])
    query += " GROUP BY e.id ORDER BY total_ot_hours DESC, e.last_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
