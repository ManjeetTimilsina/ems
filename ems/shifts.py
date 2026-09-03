"""
shifts.py
Manage shift type definitions (e.g. Morning 07:00-15:00, 8 hours).
"""

from datetime import datetime
from ems.database import get_connection


def _calc_hours(start_time, end_time):
    """Calculate the length of a shift in hours, handling overnight shifts."""
    fmt = "%H:%M"
    start = datetime.strptime(start_time, fmt)
    end = datetime.strptime(end_time, fmt)
    if end <= start:
        # overnight shift (e.g. 22:00 -> 06:00)
        end = end.replace(day=start.day + 1)
    return round((end - start).seconds / 3600, 2)


def add_shift_type(name, start_time, end_time):
    hours = _calc_hours(start_time, end_time)
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO shift_types (name, start_time, end_time, hours)
            VALUES (?, ?, ?, ?)
        """, (name, start_time, end_time, hours))
        conn.commit()
        return True, f"Shift type '{name}' added ({hours} hours)."
    except Exception as e:
        return False, f"Error adding shift type: {e}"
    finally:
        conn.close()


def update_shift_type(shift_type_id, name=None, start_time=None, end_time=None):
    conn = get_connection()
    existing = conn.execute("SELECT * FROM shift_types WHERE id = ?", (shift_type_id,)).fetchone()
    if not existing:
        conn.close()
        return False, "Shift type not found."

    new_name = name if name is not None else existing["name"]
    new_start = start_time if start_time is not None else existing["start_time"]
    new_end = end_time if end_time is not None else existing["end_time"]
    new_hours = _calc_hours(new_start, new_end)

    try:
        conn.execute("""
            UPDATE shift_types SET name = ?, start_time = ?, end_time = ?, hours = ?
            WHERE id = ?
        """, (new_name, new_start, new_end, new_hours, shift_type_id))
        conn.commit()
        return True, "Shift type updated."
    except Exception as e:
        return False, f"Error updating shift type: {e}"
    finally:
        conn.close()


def delete_shift_type(shift_type_id):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM shift_types WHERE id = ?", (shift_type_id,))
        conn.commit()
        if cur.rowcount == 0:
            return False, "Shift type not found."
        return True, "Shift type deleted."
    except Exception as e:
        return False, f"Error deleting shift type: {e}"
    finally:
        conn.close()


def list_shift_types():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM shift_types ORDER BY start_time").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_shift_type(shift_type_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM shift_types WHERE id = ?", (shift_type_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
