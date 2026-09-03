#!/usr/bin/env python3
"""
desktop_app.py — Desktop GUI (Tkinter) for the Employee Management System.

Run:
    python3 desktop_app.py

This is a thin presentation layer over the same `ems` package used by
the CLI (main.py) and the web app (app.py) — all three share one SQLite
database (ems_data.db) and one set of business-logic modules. Uses only
the Python standard library (tkinter + ttk), so no extra installs needed.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import calendar

from ems.database import initialize_database
from ems import employees as emp
from ems import shifts as sh
from ems import schedule as sc
from ems import absences as ab
from ems import overtime as ot
from ems import reports as rp
from ems import recurring as rec
from ems import exports as exp

# ---------------------------------------------------------------- theme --

BG = "#F5F4F0"
PANEL = "#FFFFFF"
INK = "#1B2430"
INK_SOFT = "#4A5568"
LINE = "#DEDBD3"
ACCENT = "#2F6F6B"
ACCENT_DARK = "#234F4C"
AMBER = "#C97F2A"
RUST = "#B24C3E"
GREEN = "#4B8B6F"

FONT_DISPLAY = ("Georgia", 18, "bold")
FONT_HEAD = ("Segoe UI", 12, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 9)


def today_str():
    return datetime.today().strftime("%Y-%m-%d")


class StyledFrame(tk.Frame):
    def __init__(self, master, **kw):
        kw.setdefault("bg", BG)
        super().__init__(master, **kw)


class Card(tk.Frame):
    """A white bordered panel, matching the web app's card style."""
    def __init__(self, master, title=None, **kw):
        kw.setdefault("bg", PANEL)
        kw.setdefault("highlightbackground", LINE)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("bd", 0)
        super().__init__(master, **kw)
        if title:
            head = tk.Label(self, text=title, bg=PANEL, fg=INK, font=FONT_HEAD, anchor="w")
            head.pack(fill="x", padx=16, pady=(14, 8))


def make_button(master, text, command, kind="ghost"):
    colors = {
        "primary": {"bg": ACCENT, "fg": "white", "activebackground": ACCENT_DARK},
        "ghost": {"bg": PANEL, "fg": INK, "activebackground": BG},
        "danger": {"bg": PANEL, "fg": RUST, "activebackground": "#F7E4E1"},
    }
    c = colors.get(kind, colors["ghost"])
    btn = tk.Button(master, text=text, command=command, font=FONT_BODY,
                     relief="flat", padx=12, pady=5, cursor="hand2", **c)
    return btn


def make_entry(master, width=22):
    e = tk.Entry(master, font=FONT_BODY, width=width, relief="solid", bd=1,
                 highlightbackground=LINE, highlightthickness=1)
    return e


def styled_treeview(master, columns, headings, widths):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Custom.Treeview", background=PANEL, fieldbackground=PANEL,
                     foreground=INK, rowheight=26, font=FONT_BODY, borderwidth=0)
    style.configure("Custom.Treeview.Heading", background="#EDEBE5", foreground=INK_SOFT,
                     font=("Segoe UI", 9, "bold"), relief="flat")
    style.map("Custom.Treeview", background=[("selected", "#E4F0EA")])

    tree = ttk.Treeview(master, columns=columns, show="headings", style="Custom.Treeview")
    for col, head, w in zip(columns, headings, widths):
        tree.heading(col, text=head)
        tree.column(col, width=w, anchor="w")
    return tree


# ============================================================== app root

class EmsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Staffing Board — Employee Management System")
        self.geometry("1180x720")
        self.configure(bg=BG)
        self.minsize(980, 600)

        initialize_database()
        if not sh.list_shift_types():
            sh.add_shift_type("Morning", "07:00", "15:00")
            sh.add_shift_type("Evening", "15:00", "23:00")
            sh.add_shift_type("Night", "23:00", "07:00")

        # Auto-generate the schedule from recurring patterns for the current
        # month and one month ahead, every time the app starts — this keeps
        # each employee's monthly schedule building itself forward without
        # manual re-entry, never further than one month out.
        rec.generate_current_and_next_month()

        self._build_shell()

    def _build_shell(self):
        # Sidebar
        sidebar = tk.Frame(self, bg=INK, width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=INK)
        brand.pack(fill="x", pady=(20, 16), padx=18)
        tk.Label(brand, text="MANAGER CONSOLE", bg=INK, fg="#8A9A97",
                  font=("Consolas", 8)).pack(anchor="w")
        tk.Label(brand, text="Staffing Board", bg=INK, fg="white",
                  font=("Georgia", 17, "bold")).pack(anchor="w", pady=(2, 0))

        self.tabs = {}
        nav_items = [
            ("Dashboard", self.show_dashboard),
            ("Employees", self.show_employees),
            ("Shift Types", self.show_shifts),
            ("Schedule", self.show_schedule),
            ("Patterns", self.show_patterns),
            ("Absences", self.show_absences),
            ("Overtime", self.show_overtime),
            ("Reports", self.show_reports),
        ]
        self.nav_buttons = {}
        for label, cmd in nav_items:
            b = tk.Button(sidebar, text=label, command=cmd, font=FONT_BODY,
                          bg=INK, fg="#C7C4BB", activebackground="#2A3542",
                          activeforeground="white", relief="flat", anchor="w",
                          padx=18, pady=9, bd=0, cursor="hand2")
            b.pack(fill="x")
            self.nav_buttons[label] = b

        # Content area (scrollable)
        outer = tk.Frame(self, bg=BG)
        outer.pack(side="right", fill="both", expand=True)

        self.canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = tk.Frame(self.canvas, bg=BG, padx=28, pady=24)
        self.content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.content_window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self.show_dashboard()

    def _set_active_nav(self, label):
        for k, b in self.nav_buttons.items():
            if k == label:
                b.configure(bg="#2A3542", fg="white")
            else:
                b.configure(bg=INK, fg="#C7C4BB")

    def clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def header(self, title, subtitle=""):
        tk.Label(self.content, text=title, font=FONT_DISPLAY, bg=BG, fg=INK).pack(anchor="w")
        if subtitle:
            tk.Label(self.content, text=subtitle, font=FONT_BODY, bg=BG, fg=INK_SOFT).pack(anchor="w", pady=(0, 16))
        else:
            tk.Frame(self.content, bg=BG, height=8).pack()

    # ========================================================= dashboard

    def show_dashboard(self):
        self._set_active_nav("Dashboard")
        self.clear_content()
        self.header("Today's Floor", f"{today_str()} — who's on, who's out, what's covered")

        date = today_str()
        todays_shifts = sc.get_schedule_for_date(date)
        year, month = datetime.today().year, datetime.today().month
        active_count = len(emp.list_employees(status="Active"))
        absences_today = [a for a in ab.list_absences() if a["absence_date"] == date]
        ot_summary = ot.overtime_summary_by_employee(year, month)
        total_ot = round(sum(r["total_ot_hours"] for r in ot_summary), 1)

        stat_row = tk.Frame(self.content, bg=BG)
        stat_row.pack(fill="x", pady=(0, 16))
        stats = [
            ("Active Employees", active_count, ACCENT),
            ("Shifts Today", len(todays_shifts), GREEN if todays_shifts else INK_SOFT),
            ("Out Today", len(absences_today), RUST if absences_today else INK_SOFT),
            ("OT Hours (month)", total_ot, AMBER if total_ot else INK_SOFT),
        ]
        for label, val, color in stats:
            box = tk.Frame(stat_row, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            box.pack(side="left", fill="both", expand=True, padx=(0, 10))
            tk.Frame(box, bg=color, width=3).pack(side="left", fill="y")
            inner = tk.Frame(box, bg=PANEL)
            inner.pack(fill="both", expand=True, padx=12, pady=10)
            tk.Label(inner, text=str(val), font=("Georgia", 22, "bold"), bg=PANEL, fg=INK).pack(anchor="w")
            tk.Label(inner, text=label.upper(), font=("Consolas", 8), bg=PANEL, fg=INK_SOFT).pack(anchor="w")

        card = Card(self.content, title="On Shift Today")
        card.pack(fill="both", expand=True)
        if todays_shifts:
            tree = styled_treeview(card, ("emp", "shift", "time", "status"),
                                    ("Employee", "Shift", "Time", "Status"), (220, 120, 140, 100))
            for s in todays_shifts:
                tree.insert("", "end", values=(f"{s['first_name']} {s['last_name']} ({s['employee_code']})",
                                                s["shift_name"], f"{s['start_time']}-{s['end_time']}", s["status"]))
            tree.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        else:
            tk.Label(card, text="No shifts scheduled for today.", bg=PANEL, fg=INK_SOFT,
                     font=FONT_BODY).pack(padx=16, pady=20)

    # ========================================================= employees

    def show_employees(self):
        self._set_active_nav("Employees")
        self.clear_content()
        self.header("Employees", "Roster, EFT, and contact details")

        toolbar = tk.Frame(self.content, bg=BG)
        toolbar.pack(fill="x", pady=(0, 10))
        make_button(toolbar, "+ Add Employee", self._open_employee_form, "primary").pack(side="left")

        search_var = tk.StringVar()
        tk.Label(toolbar, text="Search:", bg=BG, fg=INK_SOFT, font=FONT_BODY).pack(side="left", padx=(20, 4))
        search_entry = make_entry(toolbar, width=18)
        search_entry.pack(side="left")

        tk.Label(toolbar, text="Group by:", bg=BG, fg=INK_SOFT, font=FONT_BODY).pack(side="left", padx=(20, 4))
        group_var = tk.StringVar(value="None")
        group_combo = ttk.Combobox(toolbar, textvariable=group_var, state="readonly", width=14,
                                    values=["None", "Department", "Shift Type"])
        group_combo.pack(side="left")

        card = Card(self.content, title="Roster")
        card.pack(fill="both", expand=True)

        tree = styled_treeview(card, ("code", "name", "position", "eft", "status", "contact"),
                                ("Code", "Name", "Position", "EFT", "Status", "Contact"),
                                (70, 160, 140, 50, 80, 180))
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        def refresh(*_):
            for i in tree.get_children():
                tree.delete(i)
            search = search_entry.get() or None
            choice = group_var.get()

            def insert_employee(e, parent=""):
                tree.insert(parent, "end", iid=str(e["id"]),
                            values=(e["employee_code"], f"{e['first_name']} {e['last_name']}",
                                    e["position"] or "-", e["eft"], e["status"],
                                    e["email"] or e["phone"] or "-"))

            if choice == "Department":
                for label, emps in emp.list_employees_grouped(group_by="department", search=search):
                    gid = f"group::{label}"
                    tree.insert("", "end", iid=gid, open=True,
                                values=(f"— {label} ({len(emps)}) —", "", "", "", "", ""))
                    for e in emps:
                        insert_employee(e, parent=gid)
            elif choice == "Shift Type":
                for label, emps in emp.list_employees_grouped(group_by="shift_type", search=search):
                    gid = f"group::{label}"
                    tree.insert("", "end", iid=gid, open=True,
                                values=(f"— {label} ({len(emps)}) —", "", "", "", "", ""))
                    for e in emps:
                        insert_employee(e, parent=gid)
            else:
                for e in emp.list_employees(search=search):
                    insert_employee(e)

        search_entry.bind("<KeyRelease>", refresh)
        group_combo.bind("<<ComboboxSelected>>", refresh)
        refresh()

        btn_row = tk.Frame(card, bg=PANEL)
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        def get_selected():
            sel = tree.selection()
            if not sel or sel[0].startswith("group::"):
                messagebox.showinfo("Select an employee", "Please select an employee row (not a group header) first.")
                return None
            return emp.get_employee(int(sel[0]))

        def do_edit():
            e = get_selected()
            if e:
                self._open_employee_form(existing=e)

        def do_toggle_status():
            e = get_selected()
            if e:
                if e["status"] == "Active":
                    emp.deactivate_employee(e["id"])
                else:
                    emp.reactivate_employee(e["id"])
                refresh()

        def do_delete():
            e = get_selected()
            if e and messagebox.askyesno("Confirm delete",
                    f"Permanently delete {e['first_name']} {e['last_name']} and all their records?"):
                emp.delete_employee(e["id"])
                refresh()

        def do_calendar():
            e = get_selected()
            if e:
                self._open_employee_calendar(e["id"], datetime.today().year, datetime.today().month)

        def do_hours():
            e = get_selected()
            if e:
                self._open_employee_detail(e["id"], datetime.today().year, datetime.today().month)

        make_button(btn_row, "Monthly Calendar", do_calendar).pack(side="left", padx=(0, 8))
        make_button(btn_row, "Hours & Schedule", do_hours).pack(side="left", padx=(0, 8))
        make_button(btn_row, "Edit Selected", do_edit).pack(side="left", padx=(0, 8))
        make_button(btn_row, "Toggle Active/Inactive", do_toggle_status).pack(side="left", padx=(0, 8))
        make_button(btn_row, "Delete Permanently", do_delete, "danger").pack(side="left")

    def _open_employee_form(self, existing=None):
        win = tk.Toplevel(self)
        win.title("Edit Employee" if existing else "Add Employee")
        win.configure(bg=PANEL)
        win.geometry("380x460")

        fields = {}
        labels = [("employee_code", "Employee Code"), ("first_name", "First Name"),
                  ("last_name", "Last Name"), ("position", "Position"),
                  ("department", "Department"), ("eft", "EFT (1.0=full time)"),
                  ("hire_date", "Hire Date (YYYY-MM-DD)"), ("phone", "Phone"), ("email", "Email")]

        for key, label in labels:
            tk.Label(win, text=label, bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).pack(anchor="w", padx=20, pady=(10, 2))
            entry = make_entry(win, width=34)
            entry.pack(anchor="w", padx=20)
            if existing:
                val = existing.get(key, "")
                entry.insert(0, "" if val is None else str(val))
                if key == "employee_code":
                    entry.configure(state="disabled")
            elif key == "eft":
                entry.insert(0, "1.0")
            elif key == "hire_date":
                entry.insert(0, today_str())
            fields[key] = entry

        def save():
            try:
                eft_val = float(fields["eft"].get() or 1.0)
            except ValueError:
                messagebox.showerror("Invalid EFT", "EFT must be a number, e.g. 1.0 or 0.5")
                return
            if existing:
                ok, msg = emp.update_employee(
                    existing["id"], first_name=fields["first_name"].get(),
                    last_name=fields["last_name"].get(), position=fields["position"].get(),
                    department=fields["department"].get(), eft=eft_val,
                    hire_date=fields["hire_date"].get(), phone=fields["phone"].get(),
                    email=fields["email"].get())
            else:
                ok, msg = emp.add_employee(
                    fields["employee_code"].get(), fields["first_name"].get(),
                    fields["last_name"].get(), fields["position"].get(),
                    fields["department"].get(), eft_val, fields["hire_date"].get(),
                    fields["phone"].get(), fields["email"].get())
            if ok:
                win.destroy()
                self.show_employees()
            else:
                messagebox.showerror("Error", msg)

        make_button(win, "Save", save, "primary").pack(pady=16)

    # ============================================================ shifts

    def show_shifts(self):
        self._set_active_nav("Shift Types")
        self.clear_content()
        self.header("Shift Types", "Reusable shift definitions used across the schedule")

        card = Card(self.content, title="Defined Shifts")
        card.pack(fill="both", expand=True, pady=(0, 16))
        tree = styled_treeview(card, ("name", "start", "end", "hours"),
                                ("Name", "Start", "End", "Hours"), (160, 100, 100, 80))
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            for s in sh.list_shift_types():
                tree.insert("", "end", iid=s["id"], values=(s["name"], s["start_time"], s["end_time"], s["hours"]))
        refresh()

        def do_delete():
            sel = tree.selection()
            if not sel:
                return
            if messagebox.askyesno("Confirm", "Delete this shift type?"):
                sh.delete_shift_type(int(sel[0]))
                refresh()

        btns = tk.Frame(card, bg=PANEL)
        btns.pack(fill="x", padx=16, pady=(0, 14))
        make_button(btns, "Delete Selected", do_delete, "danger").pack(side="left")

        add_card = Card(self.content, title="Add Shift Type")
        add_card.pack(fill="x")
        form = tk.Frame(add_card, bg=PANEL)
        form.pack(fill="x", padx=16, pady=(0, 16))

        tk.Label(form, text="Name", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=0, sticky="w")
        name_e = make_entry(form, 18); name_e.grid(row=1, column=0, padx=(0, 10))
        tk.Label(form, text="Start (HH:MM)", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=1, sticky="w")
        start_e = make_entry(form, 10); start_e.grid(row=1, column=1, padx=(0, 10))
        tk.Label(form, text="End (HH:MM)", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=2, sticky="w")
        end_e = make_entry(form, 10); end_e.grid(row=1, column=2, padx=(0, 10))

        def add_shift():
            ok, msg = sh.add_shift_type(name_e.get(), start_e.get(), end_e.get())
            if ok:
                name_e.delete(0, "end"); start_e.delete(0, "end"); end_e.delete(0, "end")
                refresh()
            else:
                messagebox.showerror("Error", msg)

        make_button(form, "Add", add_shift, "primary").grid(row=1, column=3, padx=(10, 0))

    # ========================================================== schedule

    def show_schedule(self):
        self._set_active_nav("Schedule")
        self.clear_content()

        state = {"year": datetime.today().year, "month": datetime.today().month}

        self.header("Schedule", "Assign shifts and review monthly staffing")

        nav = tk.Frame(self.content, bg=BG)
        nav.pack(fill="x", pady=(0, 10))
        month_label = tk.Label(nav, text="", bg=BG, fg=INK, font=FONT_HEAD)
        month_label.pack(side="left")

        card = Card(self.content, title="Assign a Shift")
        card.pack(fill="x", pady=(10, 16))
        form = tk.Frame(card, bg=PANEL)
        form.pack(fill="x", padx=16, pady=(0, 16))

        emps = emp.list_employees(status="Active")
        shift_types = sh.list_shift_types()

        tk.Label(form, text="Employee", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=0, sticky="w")
        emp_var = tk.StringVar()
        emp_choices = [f"{e['first_name']} {e['last_name']} ({e['employee_code']})" for e in emps]
        emp_combo = ttk.Combobox(form, textvariable=emp_var, values=emp_choices, width=26, state="readonly")
        emp_combo.grid(row=1, column=0, padx=(0, 10))

        tk.Label(form, text="Shift", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=1, sticky="w")
        shift_var = tk.StringVar()
        shift_choices = [f"{s['name']} ({s['start_time']}-{s['end_time']})" for s in shift_types]
        shift_combo = ttk.Combobox(form, textvariable=shift_var, values=shift_choices, width=22, state="readonly")
        shift_combo.grid(row=1, column=1, padx=(0, 10))

        tk.Label(form, text="Date (YYYY-MM-DD)", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=2, sticky="w")
        date_e = make_entry(form, 14)
        date_e.insert(0, today_str())
        date_e.grid(row=1, column=2, padx=(0, 10))

        list_card = Card(self.content, title="Scheduled Shifts")
        list_card.pack(fill="both", expand=True)
        tree = styled_treeview(list_card, ("date", "emp", "shift", "time", "status"),
                                ("Date", "Employee", "Shift", "Time", "Status"), (100, 200, 110, 130, 90))
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        def refresh_list():
            for i in tree.get_children():
                tree.delete(i)
            schedule_by_date = sc.get_monthly_schedule(state["year"], state["month"])
            for date_str in sorted(schedule_by_date.keys()):
                for entry in schedule_by_date[date_str]:
                    tree.insert("", "end", iid=entry["id"],
                                values=(date_str, f"{entry['first_name']} {entry['last_name']}",
                                        entry["shift_name"], f"{entry['start_time']}-{entry['end_time']}",
                                        entry["status"]))
            month_label.configure(text=rp.month_name(state["year"], state["month"]))

        def change_month(delta):
            m = state["month"] + delta
            y = state["year"]
            if m < 1:
                m = 12; y -= 1
            elif m > 12:
                m = 1; y += 1
            state["month"], state["year"] = m, y
            refresh_list()

        make_button(nav, "< Prev", lambda: change_month(-1)).pack(side="left", padx=(16, 4))
        make_button(nav, "Next >", lambda: change_month(1)).pack(side="left")

        def do_assign():
            if not emp_var.get() or not shift_var.get() or not date_e.get():
                messagebox.showinfo("Missing info", "Please choose employee, shift, and date.")
                return
            e = emps[emp_choices.index(emp_var.get())]
            st = shift_types[shift_choices.index(shift_var.get())]
            ok, msg = sc.assign_shift(e["id"], st["id"], date_e.get())
            if ok:
                refresh_list()
            else:
                messagebox.showerror("Error", msg)

        make_button(form, "Assign", do_assign, "primary").grid(row=1, column=3, padx=(10, 0))

        status_row = tk.Frame(list_card, bg=PANEL)
        status_row.pack(fill="x", padx=16, pady=(0, 14))
        tk.Label(status_row, text="Set status of selected:", bg=PANEL, fg=INK_SOFT, font=FONT_BODY).pack(side="left")
        for status_name, button_label in (("Scheduled", "Scheduled"), ("Worked", "Worked"), ("Absent", "Absent (Sick)")):
            def make_setter(s=status_name):
                def _set():
                    sel = tree.selection()
                    if sel:
                        sc.set_status_with_sync(int(sel[0]), s)
                        refresh_list()
                return _set
            make_button(status_row, button_label, make_setter()).pack(side="left", padx=4)
        tk.Label(status_row, text="  (Personal/Vacation/Other reasons or coverage → use the Absences tab)",
                 bg=PANEL, fg=INK_SOFT, font=("Segoe UI", 8, "italic")).pack(side="left", padx=(6, 0))

        def do_remove():
            sel = tree.selection()
            if sel and messagebox.askyesno("Confirm", "Remove this shift assignment?"):
                sc.remove_schedule_entry(int(sel[0]))
                refresh_list()
        make_button(status_row, "Remove", do_remove, "danger").pack(side="left", padx=(16, 0))

        refresh_list()

    # ========================================================== patterns

    def show_patterns(self):
        self._set_active_nav("Patterns")
        self.clear_content()
        self.header("Recurring Patterns", "Set a weekly pattern once — the schedule fills itself in every month")

        card = Card(self.content, title="Add a Pattern")
        card.pack(fill="x", pady=(0, 16))
        form = tk.Frame(card, bg=PANEL)
        form.pack(fill="x", padx=16, pady=(0, 16))

        emps = emp.list_employees(status="Active")
        emp_choices = [f"{e['first_name']} {e['last_name']} ({e['employee_code']})" for e in emps]
        shift_types = sh.list_shift_types()
        shift_choices = [f"{s['name']} ({s['start_time']}-{s['end_time']})" for s in shift_types]
        weekday_choices = list(rec.WEEKDAY_NAMES)

        tk.Label(form, text="Employee", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=0, sticky="w")
        emp_var = tk.StringVar()
        ttk.Combobox(form, textvariable=emp_var, values=emp_choices, width=22, state="readonly").grid(row=1, column=0, padx=(0, 10))

        tk.Label(form, text="Shift", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=1, sticky="w")
        shift_var = tk.StringVar()
        ttk.Combobox(form, textvariable=shift_var, values=shift_choices, width=18, state="readonly").grid(row=1, column=1, padx=(0, 10))

        tk.Label(form, text="Repeats On", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=2, sticky="w")
        weekday_var = tk.StringVar()
        ttk.Combobox(form, textvariable=weekday_var, values=weekday_choices, width=12, state="readonly").grid(row=1, column=2, padx=(0, 10))

        tk.Label(form, text="Frequency", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=3, sticky="w")
        freq_var = tk.StringVar(value="Every week")
        freq_combo = ttk.Combobox(form, textvariable=freq_var, values=["Every week", "Every other week"],
                                   width=14, state="readonly")
        freq_combo.grid(row=1, column=3, padx=(0, 10))

        tk.Label(form, text="Rotation Week", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=4, sticky="w")
        week_var = tk.StringVar(value="Week 1")
        week_combo = ttk.Combobox(form, textvariable=week_var, values=["Week 1", "Week 2"],
                                   width=10, state="disabled")
        week_combo.grid(row=1, column=4, padx=(0, 10))

        def _on_freq_change(*_):
            week_combo.configure(state="readonly" if freq_var.get() == "Every other week" else "disabled")
        freq_combo.bind("<<ComboboxSelected>>", _on_freq_change)

        tk.Label(form, text="Starting (YYYY-MM-DD)", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=5, sticky="w")
        start_e = make_entry(form, 12); start_e.insert(0, today_str()); start_e.grid(row=1, column=5, padx=(0, 10))

        tk.Label(form, text="Until (optional)", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=6, sticky="w")
        end_e = make_entry(form, 12); end_e.grid(row=1, column=6, padx=(0, 10))

        list_card = Card(self.content, title="Patterns")
        list_card.pack(fill="both", expand=True)
        tree = styled_treeview(list_card, ("emp", "shift", "weekday", "from", "until", "status"),
                                ("Employee", "Shift", "Repeats", "From", "Until", "Status"),
                                (180, 130, 130, 90, 90, 70))
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            for p in rec.list_patterns():
                if p.get("frequency") == "biweekly":
                    repeats_label = f"Every other {rec.WEEKDAY_NAMES[p['weekday']]} (wk{p.get('biweekly_week', 1)})"
                else:
                    repeats_label = f"Every {rec.WEEKDAY_NAMES[p['weekday']]}"
                tree.insert("", "end", iid=p["id"], values=(
                    f"{p['first_name']} {p['last_name']}", p["shift_name"],
                    repeats_label, p["effective_start"],
                    p["effective_end"] or "ongoing", "Active" if p["active"] else "Stopped"))
        refresh()

        def do_add():
            if not emp_var.get() or not shift_var.get() or not weekday_var.get() or not start_e.get():
                messagebox.showinfo("Missing info", "Please fill employee, shift, weekday, and start date.")
                return
            e = emps[emp_choices.index(emp_var.get())]
            st = shift_types[shift_choices.index(shift_var.get())]
            weekday = weekday_choices.index(weekday_var.get())
            end_val = end_e.get().strip() or None
            frequency = "biweekly" if freq_var.get() == "Every other week" else "weekly"
            biweekly_week = 2 if week_var.get() == "Week 2" else 1
            ok, msg = rec.add_pattern(e["id"], st["id"], weekday, start_e.get(), end_val,
                                       frequency=frequency, biweekly_week=biweekly_week)
            if ok:
                refresh()
                # Immediately fill in the current and next month from the new pattern
                rec.generate_current_and_next_month()
            else:
                messagebox.showerror("Error", msg)

        make_button(form, "Add Pattern", do_add, "primary").grid(row=1, column=7, padx=(10, 0))

        btn_row = tk.Frame(list_card, bg=PANEL)
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        def do_stop():
            sel = tree.selection()
            if sel:
                rec.deactivate_pattern(int(sel[0]))
                refresh()

        def do_delete():
            sel = tree.selection()
            if sel and messagebox.askyesno("Confirm", "Delete this pattern? Already-generated shifts stay on the schedule."):
                rec.delete_pattern(int(sel[0]))
                refresh()

        make_button(btn_row, "Stop Selected", do_stop).pack(side="left", padx=(0, 8))
        make_button(btn_row, "Delete Selected", do_delete, "danger").pack(side="left")

        tk.Label(self.content,
                 text="The current and next month are auto-generated from active patterns every time the app starts.",
                 bg=BG, fg=INK_SOFT, font=("Segoe UI", 9, "italic")).pack(anchor="w", pady=(8, 0))

    # ========================================================= absences

    def show_absences(self):
        self._set_active_nav("Absences")
        self.clear_content()
        self.header("Sick / Absences", "Track absences and who covered each shift")

        card = Card(self.content, title="Record an Absence")
        card.pack(fill="x", pady=(0, 16))
        form = tk.Frame(card, bg=PANEL)
        form.pack(fill="x", padx=16, pady=(0, 16))

        emps = emp.list_employees(status="Active")
        emp_choices = [f"{e['first_name']} {e['last_name']} ({e['employee_code']})" for e in emps]

        tk.Label(form, text="Employee", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=0, sticky="w")
        emp_var = tk.StringVar()
        ttk.Combobox(form, textvariable=emp_var, values=emp_choices, width=24, state="readonly").grid(row=1, column=0, padx=(0, 10))

        tk.Label(form, text="Date", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=1, sticky="w")
        date_e = make_entry(form, 12); date_e.insert(0, today_str()); date_e.grid(row=1, column=1, padx=(0, 10))

        tk.Label(form, text="Reason", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=2, sticky="w")
        reason_var = tk.StringVar(value="Sick")
        ttk.Combobox(form, textvariable=reason_var, values=["Sick", "Personal", "Vacation", "Other"],
                     width=12, state="readonly").grid(row=1, column=2, padx=(0, 10))

        tk.Label(form, text="Covered By (optional)", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=3, sticky="w")
        cover_var = tk.StringVar()
        ttk.Combobox(form, textvariable=cover_var, values=["(none)"] + emp_choices, width=24, state="readonly").grid(row=1, column=3, padx=(0, 10))

        list_card = Card(self.content, title="Absence Log")
        list_card.pack(fill="both", expand=True)
        tree = styled_treeview(list_card, ("date", "emp", "reason", "covered"),
                                ("Date", "Employee", "Reason", "Covered By"), (100, 200, 100, 200))
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            for a in ab.list_absences():
                covered = f"{a['cov_first']} {a['cov_last']}" if a["covered_code"] else "uncovered"
                tree.insert("", "end", iid=a["id"],
                            values=(a["absence_date"], f"{a['emp_first']} {a['emp_last']}", a["reason"], covered))
        refresh()

        def do_record():
            if not emp_var.get() or not date_e.get():
                messagebox.showinfo("Missing info", "Please choose an employee and date.")
                return
            e = emps[emp_choices.index(emp_var.get())]
            covered_id = None
            if cover_var.get() and cover_var.get() != "(none)":
                covered_id = emps[emp_choices.index(cover_var.get())]["id"]
            ok, msg = ab.record_absence(e["id"], date_e.get(), reason_var.get(),
                                         covered_by_employee_id=covered_id)
            if ok:
                refresh()
            else:
                messagebox.showerror("Error", msg)

        make_button(form, "Record", do_record, "primary").grid(row=1, column=4, padx=(10, 0))

        def do_delete():
            sel = tree.selection()
            if sel and messagebox.askyesno("Confirm", "Delete this absence record?"):
                ab.delete_absence(int(sel[0]))
                refresh()
        del_row = tk.Frame(list_card, bg=PANEL)
        del_row.pack(fill="x", padx=16, pady=(0, 14))
        make_button(del_row, "Delete Selected", do_delete, "danger").pack(side="left")

    # ========================================================= overtime

    def show_overtime(self):
        self._set_active_nav("Overtime")
        self.clear_content()
        self.header("Overtime", "Log and review OT hours")

        card = Card(self.content, title="Record Overtime")
        card.pack(fill="x", pady=(0, 16))
        form = tk.Frame(card, bg=PANEL)
        form.pack(fill="x", padx=16, pady=(0, 16))

        emps = emp.list_employees(status="Active")
        emp_choices = [f"{e['first_name']} {e['last_name']} ({e['employee_code']})" for e in emps]

        tk.Label(form, text="Employee", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=0, sticky="w")
        emp_var = tk.StringVar()
        ttk.Combobox(form, textvariable=emp_var, values=emp_choices, width=22, state="readonly").grid(row=1, column=0, padx=(0, 10))

        tk.Label(form, text="Date", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=1, sticky="w")
        date_e = make_entry(form, 12); date_e.insert(0, today_str()); date_e.grid(row=1, column=1, padx=(0, 10))

        tk.Label(form, text="Hours", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=2, sticky="w")
        hours_e = make_entry(form, 8); hours_e.grid(row=1, column=2, padx=(0, 10))

        tk.Label(form, text="Reason", bg=PANEL, fg=INK_SOFT, font=("Consolas", 8)).grid(row=0, column=3, sticky="w")
        reason_e = make_entry(form, 18); reason_e.grid(row=1, column=3, padx=(0, 10))

        list_card = Card(self.content, title="Overtime Log")
        list_card.pack(fill="both", expand=True)
        tree = styled_treeview(list_card, ("date", "emp", "hours", "reason"),
                                ("Date", "Employee", "Hours", "Reason"), (100, 200, 80, 220))
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            for o in ot.list_overtime():
                tree.insert("", "end", iid=o["id"],
                            values=(o["ot_date"], f"{o['first_name']} {o['last_name']}", o["hours"], o["reason"] or "-"))
        refresh()

        def do_record():
            if not emp_var.get() or not date_e.get() or not hours_e.get():
                messagebox.showinfo("Missing info", "Please fill employee, date, and hours.")
                return
            try:
                hours_val = float(hours_e.get())
            except ValueError:
                messagebox.showerror("Invalid hours", "Hours must be a number.")
                return
            e = emps[emp_choices.index(emp_var.get())]
            ok, msg = ot.record_overtime(e["id"], date_e.get(), hours_val, reason_e.get())
            if ok:
                refresh()
            else:
                messagebox.showerror("Error", msg)

        make_button(form, "Record", do_record, "primary").grid(row=1, column=4, padx=(10, 0))

        def do_delete():
            sel = tree.selection()
            if sel and messagebox.askyesno("Confirm", "Delete this overtime record?"):
                ot.delete_overtime(int(sel[0]))
                refresh()
        del_row = tk.Frame(list_card, bg=PANEL)
        del_row.pack(fill="x", padx=16, pady=(0, 14))
        make_button(del_row, "Delete Selected", do_delete, "danger").pack(side="left")

    # ========================================================== reports

    def show_reports(self):
        self._set_active_nav("Reports")
        self.clear_content()

        state = {"year": datetime.today().year, "month": datetime.today().month}
        rec.generate_schedule_for_month_if_within_window(state["year"], state["month"])

        self.header("Monthly Reports", "Hours worked, sick leave, and OT by employee")

        nav = tk.Frame(self.content, bg=BG)
        nav.pack(fill="x", pady=(0, 10))
        month_label = tk.Label(nav, text="", bg=BG, fg=INK, font=FONT_HEAD)
        month_label.pack(side="left", padx=(0, 12))

        card = Card(self.content, title="Employee Summary — double-click a row for full detail")
        card.pack(fill="both", expand=True)
        tree = styled_treeview(card, ("name", "eft", "expected", "worked", "sick", "ot", "total"),
                                ("Employee", "EFT", "Expected Hrs", "Worked Hrs", "Sick Hrs",
                                 "OT Hrs", "Total Paid"),
                                (180, 50, 90, 90, 70, 60, 90))
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        row_data = {}

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            row_data.clear()
            rec.generate_schedule_for_month_if_within_window(state["year"], state["month"])
            for e in emp.list_employees(status="Active"):
                s = rp.employee_hours_breakdown(e["id"], state["year"], state["month"])
                name = f"{s['employee']['first_name']} {s['employee']['last_name']}"
                iid = str(e["id"])
                tree.insert("", "end", iid=iid, values=(
                    name, s["employee"]["eft"], s["expected_hours"], s["worked_hours"],
                    s["sick_hours"], s["overtime_hours"], s["total_paid_hours"]))
                row_data[iid] = e["id"]
            month_label.configure(text=rp.month_name(state["year"], state["month"]))

        def change_month(delta):
            m = state["month"] + delta
            y = state["year"]
            if m < 1:
                m = 12; y -= 1
            elif m > 12:
                m = 1; y += 1
            state["month"], state["year"] = m, y
            refresh()

        make_button(nav, "< Prev", lambda: change_month(-1)).pack(side="left", padx=(0, 4))
        make_button(nav, "Next >", lambda: change_month(1)).pack(side="left")

        def on_double_click(_event):
            sel = tree.selection()
            if sel:
                self._open_employee_detail(row_data[sel[0]], state["year"], state["month"])
        tree.bind("<Double-1>", on_double_click)

        btn_row = tk.Frame(card, bg=PANEL)
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        def do_view():
            sel = tree.selection()
            if sel:
                self._open_employee_detail(row_data[sel[0]], state["year"], state["month"])
            else:
                messagebox.showinfo("Select an employee", "Please select a row first.")
        make_button(btn_row, "View Full Detail", do_view, "primary").pack(side="left", padx=(0, 8))

        def do_export():
            default_name = f"employee-hours-{state['year']:04d}-{state['month']:02d}.xlsx"
            path = filedialog.asksaveasfilename(
                title="Export monthly summary to Excel",
                initialfile=default_name,
                defaultextension=".xlsx",
                filetypes=[("Excel workbook", "*.xlsx")],
            )
            if not path:
                return
            try:
                exp.export_monthly_summary_to_excel(state["year"], state["month"], path)
                messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            except Exception as e:
                messagebox.showerror("Export failed", str(e))
        make_button(btn_row, "Export to Excel", do_export).pack(side="left")

        refresh()

    def _open_employee_detail(self, employee_id, year, month):
        """A standalone window showing one employee's full monthly hours
        breakdown and day-by-day schedule — the 'how many hours did they
        work / how much sick leave / how much OT / what's their schedule'
        view for a single person."""
        data = rp.employee_hours_breakdown(employee_id, year, month)
        if not data:
            return

        win = tk.Toplevel(self)
        win.title(f"{data['employee']['first_name']} {data['employee']['last_name']} — {data['month_label']}")
        win.configure(bg=BG)
        win.geometry("720x640")

        state = {"year": year, "month": month}

        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=20, pady=(16, 8))
        title_lbl = tk.Label(header, text="", bg=BG, fg=INK, font=("Georgia", 16, "bold"), anchor="w")
        title_lbl.pack(anchor="w")
        sub_lbl = tk.Label(header, text="", bg=BG, fg=INK_SOFT, font=FONT_BODY, anchor="w")
        sub_lbl.pack(anchor="w")

        stat_row = tk.Frame(win, bg=BG)
        stat_row.pack(fill="x", padx=20, pady=(4, 10))
        stat_labels = {}
        for key, label, color in [("worked_hours", "HOURS WORKED", GREEN),
                                   ("sick_hours", "SICK LEAVE HRS", RUST),
                                   ("overtime_hours", "OVERTIME HRS", AMBER),
                                   ("total_paid_hours", "TOTAL PAID HRS", ACCENT)]:
            box = tk.Frame(stat_row, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            box.pack(side="left", fill="both", expand=True, padx=(0, 8))
            tk.Frame(box, bg=color, width=3).pack(side="left", fill="y")
            inner = tk.Frame(box, bg=PANEL)
            inner.pack(fill="both", expand=True, padx=10, pady=8)
            val_lbl = tk.Label(inner, text="0", font=("Georgia", 18, "bold"), bg=PANEL, fg=INK)
            val_lbl.pack(anchor="w")
            tk.Label(inner, text=label, font=("Consolas", 7), bg=PANEL, fg=INK_SOFT).pack(anchor="w")
            stat_labels[key] = val_lbl

        breakdown_lbl = tk.Label(win, text="", bg=BG, fg=INK_SOFT, font=("Consolas", 8), anchor="w")
        breakdown_lbl.pack(fill="x", padx=20, pady=(0, 8))

        sched_card = Card(win, title="Individual Schedule")
        sched_card.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        tree = styled_treeview(sched_card, ("date", "shift", "time", "hours", "status"),
                                ("Date", "Shift", "Time", "Hours", "Status"), (100, 110, 110, 60, 90))
        tree.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        nav = tk.Frame(win, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0, 16))

        def render():
            d = rp.employee_hours_breakdown(employee_id, state["year"], state["month"])
            title_lbl.configure(text=f"{d['employee']['first_name']} {d['employee']['last_name']} ({d['employee']['employee_code']})")
            sub_lbl.configure(text=f"{d['employee']['position'] or '—'} · EFT {d['employee']['eft']} · {d['month_label']}")
            for key in stat_labels:
                stat_labels[key].configure(text=str(d[key]))
            breakdown_lbl.configure(
                text=f"OT breakdown — manual: {d['manual_overtime_hours']}h · "
                     f"auto (daily): {d['auto_overtime_daily']}h · "
                     f"auto (biweekly, >80h/14d): {d['auto_overtime_biweekly']}h")
            for i in tree.get_children():
                tree.delete(i)
            for e in d["schedule_entries"]:
                tree.insert("", "end", values=(e["work_date"], e["shift_name"],
                                                f"{e['start_time']}-{e['end_time']}", e["hours"], e["status"]))

        def change_month(delta):
            m = state["month"] + delta
            y = state["year"]
            if m < 1:
                m = 12; y -= 1
            elif m > 12:
                m = 1; y += 1
            state["month"], state["year"] = m, y
            rec.generate_schedule_for_month_if_within_window(y, m)
            render()

        make_button(nav, "< Prev Month", lambda: change_month(-1)).pack(side="left", padx=(0, 8))
        make_button(nav, "Next Month >", lambda: change_month(1)).pack(side="left")

        render()

    def _open_employee_calendar(self, employee_id, year, month):
        """A standalone window showing one employee's schedule as an
        actual month calendar grid (Mon-Sun weeks), rather than a flat
        list — makes it easy to see gaps and patterns at a glance."""
        employee = emp.get_employee(employee_id)
        if not employee:
            return

        win = tk.Toplevel(self)
        win.title(f"{employee['first_name']} {employee['last_name']} — Calendar")
        win.configure(bg=BG)
        win.geometry("760x600")

        state = {"year": year, "month": month}

        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=20, pady=(16, 8))
        title_lbl = tk.Label(header, text="", bg=BG, fg=INK, font=("Georgia", 16, "bold"), anchor="w")
        title_lbl.pack(anchor="w")

        grid_frame = tk.Frame(win, bg=BG)
        grid_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        nav = tk.Frame(win, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0, 16))

        weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        def render():
            for w in grid_frame.winfo_children():
                w.destroy()

            title_lbl.configure(text=f"{employee['first_name']} {employee['last_name']} "
                                      f"({employee['employee_code']}) — {rp.month_name(state['year'], state['month'])}")

            for col, wd in enumerate(weekday_labels):
                tk.Label(grid_frame, text=wd, bg=BG, fg=INK_SOFT, font=("Consolas", 9, "bold")).grid(
                    row=0, column=col, sticky="w", padx=2, pady=(0, 4))

            weeks = rp.employee_monthly_calendar_grid(employee_id, state["year"], state["month"])
            today_str_ = today_str()
            for r, week in enumerate(weeks, start=1):
                for c, day in enumerate(week):
                    cell = tk.Frame(grid_frame, bg=PANEL, highlightbackground=LINE, highlightthickness=1,
                                     width=100, height=80)
                    cell.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)
                    cell.grid_propagate(False)
                    if day is None:
                        cell.configure(bg=BG, highlightthickness=0)
                        continue
                    if day["date"] == today_str_:
                        cell.configure(bg="#FBEEDD")
                    tk.Label(cell, text=str(day["day"]), bg=cell.cget("bg"), fg=INK,
                             font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=(2, 0))
                    for entry in day["entries"]:
                        color = {"Scheduled": INK_SOFT, "Worked": GREEN, "Absent": RUST, "Covered": GREEN}.get(
                            entry["status"], INK_SOFT)
                        tk.Label(cell, text=f"{entry['shift_name']} ({entry['status']})",
                                 bg=cell.cget("bg"), fg=color, font=("Segoe UI", 7),
                                 wraplength=95, justify="left").pack(anchor="w", padx=4)

            for col in range(7):
                grid_frame.grid_columnconfigure(col, weight=1)

        def change_month(delta):
            m = state["month"] + delta
            y = state["year"]
            if m < 1:
                m = 12; y -= 1
            elif m > 12:
                m = 1; y += 1
            state["month"], state["year"] = m, y
            rec.generate_schedule_for_month_if_within_window(y, m)
            render()

        make_button(nav, "< Prev Month", lambda: change_month(-1)).pack(side="left", padx=(0, 8))
        make_button(nav, "Next Month >", lambda: change_month(1)).pack(side="left")

        render()


def main():
    app = EmsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
