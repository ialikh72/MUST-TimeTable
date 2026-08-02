"""
main.py
=======
Streamlit UI for the MUST Timetable Management System.

Pure Streamlit -- no Flask, no Django, no FastAPI. All data access goes
through database.py; validation and export helpers come from utils.py.
This file only renders the interface and wires user actions to those two
modules.

Run with:
    streamlit run main.py
"""

import html
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st

import database as db
from utils import export_to_csv, export_to_excel, export_to_pdf, validate_non_empty, validate_time_format

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# ---------------------------------------------------------------------------
# UI styling -- same black/gold theme as before, extended (not redesigned)
# with stat cards for the new Dashboard tab and matching download-button style.
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Poppins', sans-serif; }

.stApp { background: linear-gradient(160deg, #0d0d0d 0%, #1a1a1a 100%); }

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.must-header { text-align: center; padding: 6px 0 18px; animation: fadeIn 0.7s ease; }
.must-logo {
  width: 68px; height: 68px; border-radius: 50%;
  background: linear-gradient(135deg, #f0c419, #d4a017);
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 12px; font-size: 30px;
  box-shadow: 0 4px 18px rgba(240, 196, 25, 0.35);
}
.must-title { font-size: 32px; font-weight: 700; color: #f5f5f5; margin: 0; }
.must-subtitle { font-size: 14px; color: #a3a3a3; margin-top: 4px; }

.info-pill-row { display: flex; justify-content: center; gap: 12px; margin: 16px 0 24px; flex-wrap: wrap; }
.info-pill {
  background: #161616; border: 1px solid #f0c419; border-radius: 20px;
  padding: 8px 18px; color: #f0c419; font-weight: 600; font-size: 13px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4);
}

.card {
  background: #161616; border-radius: 16px; padding: 22px 26px;
  box-shadow: 0 6px 22px rgba(0, 0, 0, 0.45); border: 1px solid #262626;
  margin-bottom: 18px; animation: fadeIn 0.6s ease;
}

.results-table {
  width: 100%; border-collapse: collapse; animation: fadeIn 0.6s ease;
}
.results-table thead th {
  text-align: left; color: #f0c419; font-weight: 700; font-size: 14px;
  padding: 12px 16px; border-bottom: 2px solid #f0c419;
}
.results-table tbody td {
  padding: 12px 16px; color: #f5f5f5; font-size: 14px;
  border-bottom: 1px solid #262626;
}
.results-table tbody tr { transition: background 0.2s ease; }
.results-table tbody tr:hover { background: #1f1f1f; }
.results-table tbody tr:last-child td { border-bottom: none; }

.empty-state { text-align: center; padding: 40px 20px; color: #a3a3a3; font-size: 16px; }

/* NEW: dashboard stat cards -- same rounded/shadow/hover language as .card */
.stat-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px; margin-bottom: 20px;
}
.stat-card {
  background: #161616; border: 1px solid #262626; border-radius: 14px;
  padding: 18px; text-align: center; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
  transition: transform 0.2s ease, box-shadow 0.2s ease; animation: fadeIn 0.6s ease;
}
.stat-card:hover { transform: translateY(-3px); box-shadow: 0 8px 22px rgba(240, 196, 25, 0.18); border-color: #f0c419; }
.stat-value { font-size: 28px; font-weight: 700; color: #f0c419; }
.stat-label { font-size: 12px; color: #a3a3a3; margin-top: 6px; }

div.stButton > button {
  background: linear-gradient(135deg, #f0c419, #d4a017); color: #0d0d0d; border: none;
  border-radius: 10px; padding: 10px 24px; font-weight: 700; font-size: 15px;
  transition: transform 0.2s ease, box-shadow 0.2s ease; box-shadow: 0 4px 14px rgba(240, 196, 25, 0.25);
  width: 100%;
}
div.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(240, 196, 25, 0.4); }

/* NEW: export buttons match the same gold gradient as regular buttons */
div.stDownloadButton > button {
  background: linear-gradient(135deg, #f0c419, #d4a017); color: #0d0d0d; border: none;
  border-radius: 10px; padding: 10px 20px; font-weight: 700; font-size: 14px;
  transition: transform 0.2s ease, box-shadow 0.2s ease; box-shadow: 0 4px 14px rgba(240, 196, 25, 0.25);
  width: 100%;
}
div.stDownloadButton > button:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(240, 196, 25, 0.4); }

div[data-baseweb="select"] > div {
  border-radius: 10px !important; border: 1px solid #f0c419 !important; background: #0d0d0d !important;
}

section[data-testid="stSidebar"] { background: #111111; border-right: 1px solid #262626; }
</style>
"""


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Shared small helpers
# ---------------------------------------------------------------------------
def render_header() -> None:
    st.markdown(
        """
        <div class="must-header">
          <div class="must-logo">🎓</div>
          <p class="must-title">MUST Timetable</p>
          <p class="must-subtitle">Mirpur University of Science &amp; Technology</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_date_day() -> None:
    now = datetime.now()
    st.markdown(
        f"""
        <div class="info-pill-row">
          <div class="info-pill">📅 {now.strftime('%d %B %Y')}</div>
          <div class="info-pill">🕒 {now.strftime('%A')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_export_buttons(df, filename_base: str) -> None:
    """CSV / Excel / PDF export buttons for any results table (Search,
    Filter, Dashboard, Bulk Import results). PDF degrades gracefully if
    reportlab is missing."""
    if df is None or df.empty:
        return
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "⬇️ CSV", data=export_to_csv(df), file_name=f"{filename_base}.csv",
        mime="text/csv", use_container_width=True,
    )
    c2.download_button(
        "⬇️ Excel", data=export_to_excel(df), file_name=f"{filename_base}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True,
    )
    pdf_bytes = export_to_pdf(df, title="MUST Timetable")
    if pdf_bytes is None:
        c3.info("PDF export needs the 'reportlab' package.")
    else:
        c3.download_button(
            "⬇️ PDF", data=pdf_bytes, file_name=f"{filename_base}.pdf",
            mime="application/pdf", use_container_width=True,
        )


def _timetable_label(row) -> str:
    return f"#{row['id']} — {row['department']} / {row['session']} / {row['section']} / {row['day']} — {row['subject']} @ {row['time']}"


# ---------------------------------------------------------------------------
# Public (student) page
# ---------------------------------------------------------------------------
def render_class_results(results: list) -> None:
    """Render (subject, teacher, room, time) rows as a clean table, or the
    empty state. No IDs, department, session, or section shown here."""
    if not results:
        st.markdown(
            '<div class="empty-state">📚 No class scheduled for this day.</div>',
            unsafe_allow_html=True,
        )
        return

    rows_html = "".join(
        f"<tr><td>{html.escape(str(subject))}</td>"
        f"<td>{html.escape(str(teacher))}</td>"
        f"<td>{html.escape(str(room))}</td>"
        f"<td>{html.escape(str(time))}</td></tr>"
        for subject, teacher, room, time in results
    )
    st.markdown(
        f"""
        <div class="card">
          <table class="results-table">
            <thead>
              <tr><th>Subject</th><th>Teacher</th><th>Room</th><th>Time</th></tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_public_page() -> None:
    render_header()
    render_date_day()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        department = st.selectbox("Department", ["Select"] + db.get_departments())
    with col2:
        session_val = st.selectbox("Session", ["Select"] + db.get_sessions())

    col3, col4 = st.columns(2)
    with col3:
        section = st.selectbox("Section", ["Select"] + db.SECTION_OPTIONS)
    with col4:
        day = st.selectbox("Day", ["Select"] + db.DAY_ORDER)

    get_clicked = st.button("📖 Show Timetable")
    st.markdown("</div>", unsafe_allow_html=True)

    if get_clicked:
        if "Select" in (department, session_val, section, day):
            st.warning("Please select a Department, Session, Section, and Day.")
        else:
            results = db.query_public_timetable(department, session_val, section, day)
            render_class_results(results)


# ---------------------------------------------------------------------------
# Admin: login
# ---------------------------------------------------------------------------
def render_admin_login() -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🔐 Admin Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            st.session_state.admin_logged_in = True
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Admin: Dashboard
# ---------------------------------------------------------------------------
def render_dashboard_tab() -> None:
    stats = db.get_dashboard_stats()
    st.markdown(
        f"""
        <div class="stat-grid">
          <div class="stat-card"><div class="stat-value">{stats['departments']}</div><div class="stat-label">Departments</div></div>
          <div class="stat-card"><div class="stat-value">{stats['sessions']}</div><div class="stat-label">Sessions</div></div>
          <div class="stat-card"><div class="stat-value">{stats['teachers']}</div><div class="stat-label">Teachers</div></div>
          <div class="stat-card"><div class="stat-value">{stats['timetable_entries']}</div><div class="stat-label">Timetable Entries</div></div>
          <div class="stat-card"><div class="stat-value">{stats['today_classes']}</div><div class="stat-label">Today's Classes ({html.escape(stats['today_name'])})</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("**Export full timetable**")
    render_export_buttons(db.fetch_all_timetable(), "must_timetable_full")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Admin: Add / Edit / Delete Timetable
# ---------------------------------------------------------------------------
def render_add_timetable_tab() -> None:
    departments = db.get_departments()
    sessions = db.get_sessions()
    teachers = db.get_teacher_names()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    if not departments or not sessions or not teachers:
        st.warning("Add at least one Department, Session, and Teacher before creating a timetable entry.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    st.caption("Adding many entries at once? Use the **📤 Bulk Import** tab to upload a CSV instead.")

    with st.form("add_timetable_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        department = c1.selectbox("Department", departments)
        session_val = c2.selectbox("Session", sessions)

        c3, c4 = st.columns(2)
        section = c3.selectbox("Section", db.SECTION_OPTIONS)
        day = c4.selectbox("Day", db.DAY_ORDER)

        c5, c6 = st.columns(2)
        teacher = c5.selectbox("Teacher", teachers)
        room = c6.text_input("Room")

        subject = st.text_input("Subject")
        time_val = st.text_input("Time (e.g. 08:30-09:50)")

        if st.form_submit_button("Add Entry"):
            if not validate_non_empty(subject, room, time_val):
                st.error("Please fill in Subject, Room, and Time.")
            elif not validate_time_format(time_val):
                st.error("Time must look like HH:MM-HH:MM (24-hour), start before end -- e.g. 08:30-09:50.")
            else:
                conflict = db.check_conflicts(department, session_val, section, day, time_val, room, teacher)
                if conflict:
                    st.error(conflict)
                else:
                    try:
                        db.add_timetable_entry(department, session_val, section, day, subject, teacher, room, time_val)
                        st.success(f"Added '{subject}' for {department} / {session_val} / {section} on {day}.")
                    except sqlite3.Error as exc:
                        st.error(f"Database error: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_import_timetable_tab() -> None:
    """Bulk-add timetable entries by uploading a CSV -- an alternative to
    filling the Add Timetable form one row at a time. Every row runs
    through the same validation and clash-checking as a manual submit;
    admin sees a per-row Added/Skipped report afterward."""
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("**Bulk-import timetable entries from a CSV file**")
    st.caption(
        "Required columns: **department, session, section, day, subject, teacher, room, time** "
        "(time as HH:MM-HH:MM, 24-hour, e.g. 08:30-09:50). Unknown departments, sessions, and "
        "teachers are created automatically (new teachers are filed under the row's department "
        "with designation 'Lecturer') -- you don't need to add them first. Every row still checks "
        "section, day, time format, and room/teacher/class clashes; rows that fail those are "
        "skipped and listed below with the reason, valid rows are inserted."
    )

    template_df = pd.DataFrame(columns=db.TIMETABLE_IMPORT_COLUMNS)
    st.download_button(
        "⬇️ Download CSV template",
        data=export_to_csv(template_df),
        file_name="must_timetable_import_template.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader("Upload CSV", type=["csv"], key="timetable_csv_uploader")
    if uploaded is None:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    try:
        import_df = pd.read_csv(uploaded, dtype=str).fillna("")
    except Exception as exc:
        st.error(f"Could not read that file as CSV: {exc}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    st.write(f"Found **{len(import_df)}** row(s) in the file.")
    st.dataframe(import_df, use_container_width=True, hide_index=True)

    if st.button("📥 Import Rows"):
        try:
            results = db.import_timetable_csv(import_df)
        except ValueError as exc:
            st.error(str(exc))
            st.markdown("</div>", unsafe_allow_html=True)
            return

        if not results:
            st.info("The file had no rows to import.")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        results_df = pd.DataFrame(results)
        added = int((results_df["status"] == "Added").sum())
        skipped = int((results_df["status"] == "Skipped").sum())

        if added:
            st.success(f"Added {added} entr{'y' if added == 1 else 'ies'}.")
        if skipped:
            st.warning(f"Skipped {skipped} row{'s' if skipped != 1 else ''} -- see reasons below.")

        display_cols = ["row"] + db.TIMETABLE_IMPORT_COLUMNS + ["status", "reason"]
        st.dataframe(results_df[display_cols], use_container_width=True, hide_index=True)
        render_export_buttons(results_df[display_cols], "must_timetable_import_results")
    st.markdown("</div>", unsafe_allow_html=True)


def render_edit_timetable_tab() -> None:
    df = db.fetch_all_timetable()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if df.empty:
        st.info("No timetable entries yet -- add one first.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    options = {int(r["id"]): _timetable_label(r) for _, r in df.iterrows()}
    selected_id = st.selectbox("Select entry to edit", list(options.keys()), format_func=lambda i: options[i])
    row = db.get_timetable_entry(selected_id)

    # Orphan-safety: if this row's department/session/teacher was since
    # renamed/deleted elsewhere, keep the stored value selectable so editing
    # doesn't crash on a value that's no longer in the current list.
    departments = db.get_departments()
    if row["department"] not in departments:
        departments = sorted(departments + [row["department"]])
    sessions = db.get_sessions()
    if row["session"] not in sessions:
        sessions = sorted(sessions + [row["session"]])
    teachers = db.get_teacher_names()
    if row["teacher"] not in teachers:
        teachers = sorted(teachers + [row["teacher"]])

    with st.form("edit_timetable_form"):
        c1, c2 = st.columns(2)
        department = c1.selectbox("Department", departments, index=departments.index(row["department"]))
        session_val = c2.selectbox("Session", sessions, index=sessions.index(row["session"]))

        c3, c4 = st.columns(2)
        section_index = db.SECTION_OPTIONS.index(row["section"]) if row["section"] in db.SECTION_OPTIONS else 0
        section = c3.selectbox("Section", db.SECTION_OPTIONS, index=section_index)
        day_index = db.DAY_ORDER.index(row["day"]) if row["day"] in db.DAY_ORDER else 0
        day = c4.selectbox("Day", db.DAY_ORDER, index=day_index)

        c5, c6 = st.columns(2)
        teacher = c5.selectbox("Teacher", teachers, index=teachers.index(row["teacher"]))
        room = c6.text_input("Room", value=row["room"])

        subject = st.text_input("Subject", value=row["subject"])
        time_val = st.text_input("Time", value=row["time"])

        if st.form_submit_button("Save Changes"):
            if not validate_non_empty(subject, room, time_val):
                st.error("Please fill in Subject, Room, and Time.")
            elif not validate_time_format(time_val):
                st.error("Time must look like HH:MM-HH:MM (24-hour), start before end.")
            else:
                conflict = db.check_conflicts(
                    department, session_val, section, day, time_val, room, teacher, exclude_id=selected_id
                )
                if conflict:
                    st.error(conflict)
                else:
                    try:
                        db.update_timetable_entry(
                            selected_id, department, session_val, section, day, subject, teacher, room, time_val
                        )
                        st.success("Entry updated.")
                        st.rerun()
                    except sqlite3.Error as exc:
                        st.error(f"Database error: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_delete_timetable_tab() -> None:
    df = db.fetch_all_timetable()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if df.empty:
        st.info("No timetable entries yet.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    options = {int(r["id"]): _timetable_label(r) for _, r in df.iterrows()}
    selected_id = st.selectbox(
        "Select entry to delete", list(options.keys()), format_func=lambda i: options[i], key="delete_tt_select"
    )
    row = db.get_timetable_entry(selected_id)

    st.markdown(
        f"""
        <div class="empty-state" style="text-align:left;">
          You're about to delete <strong>{html.escape(row['subject'])}</strong> —
          {html.escape(row['department'])} / {html.escape(row['session'])} / {html.escape(row['section'])} /
          {html.escape(row['day'])} at {html.escape(row['time'])}, room {html.escape(row['room'])},
          taught by {html.escape(row['teacher'])}.
        </div>
        """,
        unsafe_allow_html=True,
    )
    confirm = st.checkbox("Yes, I want to permanently delete this entry.")
    if st.button("🗑️ Delete Entry", disabled=not confirm):
        try:
            db.delete_timetable_entry(selected_id)
            st.success("Entry deleted.")
            st.rerun()
        except sqlite3.Error as exc:
            st.error(f"Database error: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Admin: Search / Filter
# ---------------------------------------------------------------------------
def render_search_tab() -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    keyword = st.text_input("Search keyword (subject, teacher, room, department, session, section, day)")
    if keyword:
        results = db.search_timetable(keyword)
        if results.empty:
            st.info("No matches found.")
        else:
            st.dataframe(results, use_container_width=True, hide_index=True)
            render_export_buttons(results, "must_timetable_search")
    st.markdown("</div>", unsafe_allow_html=True)


def render_filter_tab() -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    department = c1.selectbox("Department", ["All"] + db.get_departments(), key="f_dept")
    session_val = c2.selectbox("Session", ["All"] + db.get_sessions(), key="f_sess")
    section = c3.selectbox("Section", ["All"] + db.SECTION_OPTIONS, key="f_sec")

    c4, c5 = st.columns(2)
    day = c4.selectbox("Day", ["All"] + db.DAY_ORDER, key="f_day")
    teacher = c5.selectbox("Teacher", ["All"] + db.get_teacher_names(), key="f_teacher")

    results = db.filter_timetable(department, session_val, section, day, teacher)
    if results.empty:
        st.info("No entries match this filter.")
    else:
        st.dataframe(results, use_container_width=True, hide_index=True)
        render_export_buttons(results, "must_timetable_filtered")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Admin: Departments / Sessions / Teachers management
# ---------------------------------------------------------------------------
def render_departments_tab() -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("**Add a department**")
    c1, c2 = st.columns([3, 1])
    new_name = c1.text_input(
        "Department name", key="new_dept_input", label_visibility="collapsed", placeholder="e.g. Chemical Engineering"
    )
    if c2.button("➕ Add", key="add_dept_btn"):
        name = new_name.strip()
        if not name:
            st.error("Enter a department name.")
        elif name in db.get_departments():
            st.warning(f"'{name}' already exists.")
        else:
            db.add_department(name)
            st.success(f"Department '{name}' added.")
            st.rerun()

    st.markdown("---")
    st.markdown("**Existing departments**")
    departments = db.get_departments()
    if not departments:
        st.info("No departments yet -- add one above.")
    else:
        for dept in departments:
            col_a, col_b, col_c, col_d = st.columns([3, 3, 1, 1])
            col_a.write(f"🏛️ {dept}")
            usage = db.count_department_usage(dept)
            col_b.write(f"{usage['teachers']} teachers, {usage['timetable_entries']} entries")

            edit_key = f"edit_dept_{dept}"
            if col_c.button("✏️", key=f"edit_dept_btn_{dept}"):
                st.session_state[edit_key] = not st.session_state.get(edit_key, False)
            if col_d.button("🗑️", key=f"del_dept_btn_{dept}"):
                db.delete_department(dept)
                st.success(f"'{dept}' deleted.")
                st.rerun()

            if st.session_state.get(edit_key):
                new_val = st.text_input("Rename to", value=dept, key=f"rename_dept_input_{dept}")
                if st.button("Save rename", key=f"save_dept_rename_{dept}"):
                    new_val = new_val.strip()
                    if not new_val:
                        st.error("Name can't be empty.")
                    elif new_val != dept and new_val in db.get_departments():
                        st.warning(f"'{new_val}' already exists.")
                    else:
                        db.rename_department(dept, new_val)
                        st.session_state[edit_key] = False
                        st.success(f"Renamed to '{new_val}'.")
                        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_sessions_tab() -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("**Add a session**")
    c1, c2 = st.columns([3, 1])
    new_year = c1.text_input(
        "Session year", key="new_session_input", label_visibility="collapsed", placeholder="e.g. 2026"
    )
    if c2.button("➕ Add", key="add_sess_btn"):
        year = new_year.strip()
        if not year:
            st.error("Enter a session year.")
        elif not year.isdigit():
            st.error("Session year must be numeric, e.g. 2026.")
        elif year in db.get_sessions():
            st.warning(f"Session {year} already exists.")
        else:
            db.add_session(year)
            st.success(f"Session {year} added.")
            st.rerun()

    st.markdown("---")
    st.markdown("**Existing sessions**")
    sessions = db.get_sessions()
    if not sessions:
        st.info("No sessions yet -- add one above.")
    else:
        for year in sessions:
            col_a, col_b, col_c, col_d = st.columns([3, 3, 1, 1])
            col_a.write(f"📅 {year}")
            count = db.count_session_usage(year)
            col_b.write(f"{count} timetable entr{'y' if count == 1 else 'ies'}")

            edit_key = f"edit_sess_{year}"
            if col_c.button("✏️", key=f"edit_sess_btn_{year}"):
                st.session_state[edit_key] = not st.session_state.get(edit_key, False)
            if col_d.button("🗑️", key=f"del_sess_btn_{year}"):
                db.delete_session(year)
                st.success(f"Session {year} deleted.")
                st.rerun()

            if st.session_state.get(edit_key):
                new_val = st.text_input("Rename to", value=year, key=f"rename_sess_input_{year}")
                if st.button("Save rename", key=f"save_sess_rename_{year}"):
                    new_val = new_val.strip()
                    if not new_val.isdigit():
                        st.error("Session year must be numeric.")
                    elif new_val != year and new_val in db.get_sessions():
                        st.warning(f"Session {new_val} already exists.")
                    else:
                        db.rename_session(year, new_val)
                        st.session_state[edit_key] = False
                        st.success(f"Renamed to {new_val}.")
                        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_teachers_tab() -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    departments = db.get_departments()

    st.markdown("**Add a teacher**")
    if not departments:
        st.warning("Add a Department first (Departments tab) before adding teachers.")
    else:
        with st.form("add_teacher_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Teacher name")
            department = c2.selectbox("Department", departments)
            designation = c3.text_input("Designation", placeholder="e.g. Lecturer")
            if st.form_submit_button("➕ Add Teacher"):
                if not validate_non_empty(name, designation):
                    st.error("Please fill in Name and Designation.")
                else:
                    db.add_teacher(name.strip(), department, designation.strip())
                    st.success(f"Teacher '{name}' added.")
                    st.rerun()

    st.markdown("---")
    st.markdown("**Existing teachers**")
    teachers = db.get_teachers()
    if teachers.empty:
        st.info("No teachers yet.")
    else:
        for _, t in teachers.iterrows():
            tid = int(t["id"])
            col_a, col_b, col_c, col_d, col_e = st.columns([2, 2, 2, 1, 1])
            col_a.write(f"👤 {t['teacher_name']}")
            col_b.write(t["department"])
            col_c.write(t["designation"])

            edit_key = f"edit_teacher_{tid}"
            if col_d.button("✏️", key=f"edit_teacher_btn_{tid}"):
                st.session_state[edit_key] = not st.session_state.get(edit_key, False)
            if col_e.button("🗑️", key=f"del_teacher_btn_{tid}"):
                db.delete_teacher(tid)
                st.success(f"'{t['teacher_name']}' deleted.")
                st.rerun()

            usage = db.count_teacher_usage(t["teacher_name"])
            if usage:
                st.caption(f"{usage} timetable entr{'y' if usage == 1 else 'ies'} reference this teacher.")

            if st.session_state.get(edit_key):
                with st.form(f"edit_teacher_form_{tid}"):
                    ec1, ec2, ec3 = st.columns(3)
                    new_name = ec1.text_input("Name", value=t["teacher_name"])
                    dept_options = departments if t["department"] in departments else sorted(departments + [t["department"]])
                    new_dept = ec2.selectbox("Department", dept_options, index=dept_options.index(t["department"]))
                    new_designation = ec3.text_input("Designation", value=t["designation"])
                    if st.form_submit_button("Save"):
                        if not validate_non_empty(new_name, new_designation):
                            st.error("Please fill in Name and Designation.")
                        else:
                            db.update_teacher(tid, new_name.strip(), new_dept, new_designation.strip())
                            st.session_state[edit_key] = False
                            st.success("Teacher updated.")
                            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Admin: panel shell
# ---------------------------------------------------------------------------
def render_admin_panel() -> None:
    header_col, logout_col = st.columns([5, 1])
    with header_col:
        st.markdown('<p class="must-title" style="font-size:26px;">⚙️ Admin Panel</p>', unsafe_allow_html=True)
    with logout_col:
        if st.button("Logout"):
            st.session_state.admin_logged_in = False
            st.rerun()

    (
        tab_dashboard, tab_add, tab_import, tab_edit, tab_delete, tab_search,
        tab_filter, tab_departments, tab_sessions, tab_teachers,
    ) = st.tabs(
        [
            "📊 Dashboard", "➕ Add Timetable", "📤 Bulk Import", "✏️ Edit Timetable", "🗑️ Delete Timetable",
            "🔍 Search", "🧭 Filter", "🏛️ Departments", "🗓️ Sessions", "👤 Teachers",
        ]
    )
    with tab_dashboard:
        render_dashboard_tab()
    with tab_add:
        render_add_timetable_tab()
    with tab_import:
        render_import_timetable_tab()
    with tab_edit:
        render_edit_timetable_tab()
    with tab_delete:
        render_delete_timetable_tab()
    with tab_search:
        render_search_tab()
    with tab_filter:
        render_filter_tab()
    with tab_departments:
        render_departments_tab()
    with tab_sessions:
        render_sessions_tab()
    with tab_teachers:
        render_teachers_tab()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="MUST Timetable", page_icon="🎓", layout="centered")

    try:
        db.init_database()
    except sqlite3.Error as exc:
        st.error(f"Could not initialize the database: {exc}")
        st.stop()

    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    inject_css()

    page = st.sidebar.radio("Navigation", ["🏠 Student View", "🔐 Admin Panel"])

    if page == "🏠 Student View":
        render_public_page()
    else:
        if st.session_state.admin_logged_in:
            render_admin_panel()
        else:
            render_admin_login()


if __name__ == "__main__":
    main()