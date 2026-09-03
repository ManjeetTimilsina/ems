"""
employees.py
CRUD operations for employee records.
"""

from ems.database import get_connection


def add_employee(employee_code, first_name, last_name, position="", department="",
                  eft=1.0, hire_date="", phone="", email="", notes=""):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO employees
                (employee_code, first_name, last_name, position, department,
                 eft, hire_date, phone, email, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?)
        """, (employee_code, first_name, last_name, position, department,
              eft, hire_date, phone, email, notes))
        conn.commit()
        return True, "Employee added successfully."
    except Exception as e:
        return False, f"Error adding employee: {e}"
    finally:
        conn.close()


def update_employee(employee_id, **fields):
    """Update arbitrary fields of an employee. fields keys must be valid columns."""
    if not fields:
        return False, "No fields provided to update."
    valid_cols = {"employee_code", "first_name", "last_name", "position", "department",
                  "eft", "hire_date", "phone", "email", "status", "notes"}
    updates = {k: v for k, v in fields.items() if k in valid_cols}
    if not updates:
        return False, "No valid fields to update."

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [employee_id]

    conn = get_connection()
    try:
        cur = conn.execute(f"UPDATE employees SET {set_clause} WHERE id = ?", values)
        conn.commit()
        if cur.rowcount == 0:
            return False, "No employee found with that ID."
        return True, "Employee updated successfully."
    except Exception as e:
        return False, f"Error updating employee: {e}"
    finally:
        conn.close()


def deactivate_employee(employee_id):
    return update_employee(employee_id, status="Inactive")


def reactivate_employee(employee_id):
    return update_employee(employee_id, status="Active")


def delete_employee(employee_id):
    """Hard delete. Cascades to schedule/absence/overtime records."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
        conn.commit()
        if cur.rowcount == 0:
            return False, "No employee found with that ID."
        return True, "Employee deleted permanently."
    except Exception as e:
        return False, f"Error deleting employee: {e}"
    finally:
        conn.close()


def get_employee(employee_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def find_employee_by_code(employee_code):
    conn = get_connection()
    row = conn.execute("SELECT * FROM employees WHERE employee_code = ?", (employee_code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_employees(status=None, search=None):
    """List employees, optionally filtered by status ('Active'/'Inactive')
    and/or a search string matched against name or employee_code."""
    conn = get_connection()
    query = "SELECT * FROM employees WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (first_name LIKE ? OR last_name LIKE ? OR employee_code LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    query += " ORDER BY last_name, first_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def primary_shift_for_employee(employee_id):
    """The shift type this employee most commonly works — based on their
    active recurring patterns first, falling back to whichever shift
    appears most often in the current month's schedule if they have no
    patterns set up. Returns None if there's nothing to go on yet."""
    conn = get_connection()
    row = conn.execute("""
        SELECT st.id, st.name, COUNT(*) AS cnt
        FROM recurring_patterns rp
        JOIN shift_types st ON st.id = rp.shift_type_id
        WHERE rp.employee_id = ? AND rp.active = 1
        GROUP BY st.id
        ORDER BY cnt DESC, st.name
        LIMIT 1
    """, (employee_id,)).fetchone()
    if row:
        conn.close()
        return {"id": row["id"], "name": row["name"]}

    import datetime
    this_month = datetime.date.today().strftime("%Y-%m")
    row2 = conn.execute("""
        SELECT st.id, st.name, COUNT(*) AS cnt
        FROM schedule s
        JOIN shift_types st ON st.id = s.shift_type_id
        WHERE s.employee_id = ? AND strftime('%Y-%m', s.work_date) = ?
        GROUP BY st.id
        ORDER BY cnt DESC, st.name
        LIMIT 1
    """, (employee_id, this_month)).fetchone()
    conn.close()
    return {"id": row2["id"], "name": row2["name"]} if row2 else None


def list_employees_grouped(group_by="department", status=None, search=None):
    """Employees grouped for easy browsing. group_by: 'department' or
    'shift_type'. Returns a list of (group_label, [employee, ...]) tuples,
    sorted alphabetically with "Unassigned" always last."""
    employees = list_employees(status=status, search=search)
    groups = {}
    for e in employees:
        if group_by == "shift_type":
            shift = primary_shift_for_employee(e["id"])
            key = shift["name"] if shift else "Unassigned"
        else:
            key = e["department"] or "Unassigned"
        groups.setdefault(key, []).append(e)
    return sorted(groups.items(), key=lambda kv: (kv[0] == "Unassigned", kv[0]))
