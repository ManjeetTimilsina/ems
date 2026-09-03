"""
database.py
Handles the SQLite connection and schema (table) creation for the
Employee Management System.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ems_data.db")


def get_connection():
    """Return a SQLite connection with foreign keys enabled and Row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    """Create all tables if they do not already exist."""
    conn = get_connection()
    cur = conn.cursor()

    # Employees: EFT = Employment Full-Time equivalent (e.g. 1.0 = full time,
    # 0.5 = half time). Used to calculate expected monthly hours.
    # ot_daily_threshold_hours: optional per-employee override for daily
    # overtime. Usually left NULL — daily OT is normally derived
    # automatically from each day's own scheduled shift length (so mixed
    # 8h/12h shift types just work with no configuration), but this can
    # force a fixed number for an employee that doesn't fit that pattern.
    # ot_biweekly_threshold_hours: optional per-employee override for the
    # biweekly (14-day) overtime threshold — NULL means "use the global
    # default".
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT UNIQUE NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            position TEXT,
            department TEXT,
            eft REAL NOT NULL DEFAULT 1.0,
            hire_date TEXT,
            phone TEXT,
            email TEXT,
            status TEXT NOT NULL DEFAULT 'Active',   -- Active / Inactive
            notes TEXT,
            ot_daily_threshold_hours REAL,
            ot_biweekly_threshold_hours REAL
        )
    """)
    # Migration: existing databases created before these columns existed
    # won't have them yet — add them in place rather than requiring
    # anyone to delete/recreate their data.
    existing_emp_cols = {row["name"] for row in cur.execute("PRAGMA table_info(employees)")}
    if "ot_daily_threshold_hours" not in existing_emp_cols:
        cur.execute("ALTER TABLE employees ADD COLUMN ot_daily_threshold_hours REAL")
    if "ot_biweekly_threshold_hours" not in existing_emp_cols:
        cur.execute("ALTER TABLE employees ADD COLUMN ot_biweekly_threshold_hours REAL")
    # ot_weekly_threshold_hours is retired (replaced by biweekly) but left
    # in place if it exists on an older database, rather than dropped, to
    # avoid requiring a destructive migration — it's simply unused now.


    # Shift type definitions (e.g. Morning 07:00-15:00)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shift_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            start_time TEXT NOT NULL,   -- HH:MM (24h)
            end_time TEXT NOT NULL,     -- HH:MM (24h)
            hours REAL NOT NULL         -- length of shift in hours
        )
    """)

    # Monthly / daily schedule: one row = one employee assigned to one
    # shift on one date.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            shift_type_id INTEGER NOT NULL,
            work_date TEXT NOT NULL,     -- YYYY-MM-DD
            status TEXT NOT NULL DEFAULT 'Scheduled',  -- Scheduled/Worked/Absent/Covered
            notes TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE,
            FOREIGN KEY (shift_type_id) REFERENCES shift_types (id) ON DELETE CASCADE,
            UNIQUE (employee_id, work_date, shift_type_id)
        )
    """)

    # Sick / other absence records, with optional employee who covered it.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS absences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            absence_date TEXT NOT NULL,      -- YYYY-MM-DD
            reason TEXT NOT NULL DEFAULT 'Sick',  -- Sick/Personal/Vacation/Other
            schedule_id INTEGER,             -- optional link to the missed shift
            covered_by_employee_id INTEGER,  -- who covered, if anyone
            notes TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE,
            FOREIGN KEY (schedule_id) REFERENCES schedule (id) ON DELETE SET NULL,
            FOREIGN KEY (covered_by_employee_id) REFERENCES employees (id) ON DELETE SET NULL
        )
    """)

    # Overtime records
    cur.execute("""
        CREATE TABLE IF NOT EXISTS overtime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            ot_date TEXT NOT NULL,        -- YYYY-MM-DD
            hours REAL NOT NULL,
            reason TEXT,
            approved_by TEXT,
            notes TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE
        )
    """)

    # Recurring shift patterns, used to auto-generate the schedule month by
    # month (e.g. "Jane works Morning every Monday" or "...every other
    # Monday, week 1 of the 2-week rotation").
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recurring_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            shift_type_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL,        -- 0=Monday ... 6=Sunday
            frequency TEXT NOT NULL DEFAULT 'weekly',  -- 'weekly' or 'biweekly'
            biweekly_week INTEGER NOT NULL DEFAULT 1,  -- 1 or 2: which week of the 2-week rotation this applies to (biweekly only)
            effective_start TEXT NOT NULL,   -- YYYY-MM-DD, pattern applies from this date;
                                              -- also the anchor date for the biweekly rotation
            effective_end TEXT,              -- YYYY-MM-DD, NULL = ongoing / no end
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE,
            FOREIGN KEY (shift_type_id) REFERENCES shift_types (id) ON DELETE CASCADE
        )
    """)
    # Migration: existing databases created before these columns existed
    # won't have them yet — add them in place, defaulting existing
    # patterns to 'weekly'/week 1 (their prior, only behavior) rather than
    # requiring anyone to delete/recreate their data.
    existing_pattern_cols = {row["name"] for row in cur.execute("PRAGMA table_info(recurring_patterns)")}
    if "frequency" not in existing_pattern_cols:
        cur.execute("ALTER TABLE recurring_patterns ADD COLUMN frequency TEXT NOT NULL DEFAULT 'weekly'")
    if "biweekly_week" not in existing_pattern_cols:
        cur.execute("ALTER TABLE recurring_patterns ADD COLUMN biweekly_week INTEGER NOT NULL DEFAULT 1")

    conn.commit()
    conn.close()
