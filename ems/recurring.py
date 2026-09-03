"""
recurring.py
Recurring weekly shift patterns (e.g. "Jane works Morning every Mon/Wed/Fri
starting 2026-01-01"). generate_schedule_for_month() turns those patterns
into real schedule rows for a given month — call it whenever a month is
opened and it will fill in only what's missing, so the schedule keeps
building itself forward without manual re-entry each month.
"""

import calendar
import datetime

from ems.database import get_connection
from ems import schedule as sc

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def add_pattern(employee_id, shift_type_id, weekday, effective_start, effective_end=None, frequency='weekly', biweekly_week=1, notes=""):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO recurring_patterns
                (employee_id, shift_type_id, weekday, effective_start, effective_end, frequency, biweekly_week, active, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (employee_id, shift_type_id, weekday, effective_start, effective_end, frequency, biweekly_week, notes))
        conn.commit()
        return True, f"Recurring pattern added ({WEEKDAY_NAMES[weekday]})."
    except Exception as e:
        return False, f"Error adding pattern: {e}"
    finally:
        conn.close()


def deactivate_pattern(pattern_id):
    conn = get_connection()
    try:
        cur = conn.execute("UPDATE recurring_patterns SET active = 0 WHERE id = ?", (pattern_id,))
        conn.commit()
        if cur.rowcount == 0:
            return False, "Pattern not found."
        return True, "Pattern deactivated (existing schedule entries are kept)."
    except Exception as e:
        return False, f"Error deactivating pattern: {e}"
    finally:
        conn.close()


def delete_pattern(pattern_id):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM recurring_patterns WHERE id = ?", (pattern_id,))
        conn.commit()
        if cur.rowcount == 0:
            return False, "Pattern not found."
        return True, "Pattern deleted."
    except Exception as e:
        return False, f"Error deleting pattern: {e}"
    finally:
        conn.close()


def list_patterns(employee_id=None, active_only=False):
    conn = get_connection()
    query = """
        SELECT rp.id, rp.employee_id, rp.shift_type_id, rp.weekday,
               rp.frequency, rp.biweekly_week,
               rp.effective_start, rp.effective_end, rp.active, rp.notes,
               e.employee_code, e.first_name, e.last_name,
               st.name AS shift_name, st.start_time, st.end_time
        FROM recurring_patterns rp
        JOIN employees e ON e.id = rp.employee_id
        JOIN shift_types st ON st.id = rp.shift_type_id
        WHERE 1=1
    """
    params = []
    if employee_id:
        query += " AND rp.employee_id = ?"
        params.append(employee_id)
    if active_only:
        query += " AND rp.active = 1"
    query += " ORDER BY e.last_name, rp.weekday"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_employee_pattern_schedule(employee_id):
    """Delete that employee's recurring patterns and all generated schedule rows."""
    conn = get_connection()
    try:
        pattern_rows = conn.execute(
            "DELETE FROM recurring_patterns WHERE employee_id = ?",
            (employee_id,),
        )
        generated_rows = conn.execute(
            "DELETE FROM schedule WHERE employee_id = ? AND notes = ?",
            (employee_id, "Auto-generated from recurring pattern"),
        )
        conn.commit()
        return {
            "patterns_deleted": pattern_rows.rowcount,
            "generated_shifts_removed": generated_rows.rowcount,
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def generate_schedule_for_month(year, month):
    patterns = list_patterns(active_only=True)
    if not patterns:
        return 0

    last_day = calendar.monthrange(year, month)[1]
    created = 0
    for day in range(1, last_day + 1):
        date_obj = datetime.date(year, month, day)
        date_str = date_obj.strftime("%Y-%m-%d")
        weekday = date_obj.weekday()  # Monday=0 ... Sunday=6

        for p in patterns:
            if p["weekday"] != weekday:
                continue
            if date_str < p["effective_start"]:
                continue
            if p["effective_end"] and date_str > p["effective_end"]:
                continue
            
            # --- FIXED BIWEEKLY CHECK ---
            if p.get("frequency") == "biweekly":
                # Safely parse the start date string to a date object
                start_date = datetime.datetime.strptime(p["effective_start"], "%Y-%m-%d").date()
                
                # Find the Monday of both weeks to calculate pure calendar week differences
                start_monday = start_date - datetime.timedelta(days=start_date.weekday())
                current_monday = date_obj - datetime.timedelta(days=date_obj.weekday())
                
                # Calculate absolute weeks elapsed
                weeks_elapsed = (current_monday - start_monday).days // 7
                
                # Determine current cycle week (1 or 2)
                current_cycle_week = (weeks_elapsed % 2) + 1
                
                # Skip if it doesn't match the designated pattern rotation week
                if current_cycle_week != int(p.get("biweekly_week", 1)):
                    continue

            ok, _ = sc.assign_shift(
                p["employee_id"], p["shift_type_id"], date_str,
                status="Scheduled", notes="Auto-generated from recurring pattern",
            )
            if ok:
                created += 1
    return created


def current_and_next_month():
    """(year, month) for today, and (year, month) for the month right
    after it — the only two months that should ever be auto-populated
    from recurring patterns without an explicit, deliberate action."""
    today = datetime.date.today()
    next_month = 1 if today.month == 12 else today.month + 1
    next_year = today.year + 1 if today.month == 12 else today.year
    return (today.year, today.month), (next_year, next_month)


def is_within_auto_window(year, month):
    """True if (year, month) is the current calendar month or the one
    immediately following it. Any code path that auto-generates a
    schedule just because a page happened to be viewed (as opposed to an
    explicit 'generate this month' button) should check this first, so
    browsing further ahead in the Schedule view doesn't silently spawn
    shifts many months in advance — only the current and next month ever
    fill in automatically."""
    cur, nxt = current_and_next_month()
    return (year, month) in (cur, nxt)


def generate_current_and_next_month():
    """Generate schedule entries for the current calendar month and the
    one immediately following it, from all active patterns — nothing
    further out. This is what keeps the schedule filled in exactly one
    month ahead, automatically, every time the app is used (e.g. in
    August this creates August + September; in September it creates
    September + October). Safe to call repeatedly."""
    cur, nxt = current_and_next_month()
    created = generate_schedule_for_month(*cur)
    created += generate_schedule_for_month(*nxt)
    return created


def generate_schedule_for_month_if_within_window(year, month):
    """Like generate_schedule_for_month(), but only actually generates
    anything if (year, month) is the current or next calendar month —
    use this at any page/view that shouldn't be able to force-generate
    arbitrary future months just by being opened. Returns 0 (and does
    nothing) for months outside that window; use
    generate_schedule_for_month() directly for an explicit, deliberate
    "generate this month" action that should work for any month.

    When (year, month) IS within the window, this tops up BOTH the
    current and next month together (not just whichever one triggered
    the call) — that's what keeps a long-running web server's "next
    month" schedule populated continuously, rather than only right after
    the process starts."""
    if not is_within_auto_window(year, month):
        return 0
    return generate_current_and_next_month()

