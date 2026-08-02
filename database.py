"""
database.py
===========
All SQLite access for the MUST Timetable Management System: schema
creation/auto-repair, default seeding, and CRUD for Departments, Sessions,
Teachers, and Timetable -- plus the conflict checks that back Add/Edit
Timetable (duplicate class slot, room clash, teacher clash), plus bulk
CSV import for the timetable.

Pure sqlite3, parameterized queries throughout, no ORM. No Streamlit import
here either -- this module is UI-agnostic and safe to unit test directly.
"""

import os
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Optional

import pandas as pd

from utils import parse_time_range, time_ranges_overlap, validate_non_empty, validate_time_format

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database_backup.db")

DEPARTMENTS_COLUMNS = ["id", "department_name"]
SESSIONS_COLUMNS = ["id", "session"]
TEACHERS_COLUMNS = ["id", "teacher_name", "department", "designation"]
TIMETABLE_COLUMNS = ["id", "department", "session", "section", "day", "subject", "teacher", "room", "time"]

DEFAULT_DEPARTMENTS = [
    "Software Engineering",
    "Computer Science",
    "Civil Engineering",
    "Mechanical Engineering",
    "Electrical Engineering",
]
DEFAULT_SESSIONS = ["2022", "2023", "2024", "2025"]

# Fixed (not admin-managed) choices, matching the spec exactly.
SECTION_OPTIONS = ["A", "B"]
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]  # no Sunday

# Columns expected in a bulk-import CSV, in this exact order.
TIMETABLE_IMPORT_COLUMNS = ["department", "session", "section", "day", "subject", "teacher", "room", "time"]

SAMPLE_TEACHERS = [
    # teacher_name, department, designation
    ("Muhammad Ali", "Computer Science", "Lecturer"),
    ("Ayesha Khan", "Software Engineering", "Assistant Professor"),
    ("Bilal Ahmed", "Electrical Engineering", "Associate Professor"),
]

SAMPLE_TIMETABLE = [
    # department, session, section, day, subject, teacher, room, time
    ("Computer Science", "2022", "A", "Monday", "Programming Fundamentals", "Muhammad Ali", "Lab-2", "08:30-09:50"),
    ("Computer Science", "2022", "A", "Monday", "Discrete Mathematics", "Muhammad Ali", "D-101", "10:00-11:20"),
    ("Computer Science", "2022", "A", "Tuesday", "Database Systems", "Muhammad Ali", "D-102", "08:30-09:50"),
    ("Software Engineering", "2023", "B", "Monday", "Web Engineering", "Ayesha Khan", "B-205", "09:00-10:20"),
    ("Software Engineering", "2023", "B", "Wednesday", "Software Design", "Ayesha Khan", "B-206", "10:30-11:50"),
    ("Electrical Engineering", "2022", "A", "Thursday", "Circuit Analysis", "Bilal Ahmed", "E-101", "08:30-09:50"),
]


# ---------------------------------------------------------------------------
# Connection + schema management
# ---------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    print("DATABASE PATH:", DB_PATH)
    return sqlite3.connect(DB_PATH, check_same_thread=False)
    """Fresh connection per call. Streamlit reruns the whole script on every
    interaction, so short-lived connections are simplest and avoid any
    cross-thread sharing problems."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _columns(conn: sqlite3.Connection, table: str) -> list:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _schema_matches(conn: sqlite3.Connection, table: str, expected: list) -> bool:
    cols = _columns(conn, table)
    return set(cols) == set(expected) and len(cols) == len(expected)


def _ensure_table(conn, table_name, expected_columns, create_sql, seed_fn=None) -> None:
    """Generic create-if-missing / auto-repair-if-wrong-schema / seed-if-empty,
    shared by all four tables below."""
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone() is not None

    if exists and not _schema_matches(conn, table_name, expected_columns):
        conn.execute(f"DROP TABLE {table_name}")
        exists = False

    if not exists:
        conn.execute(create_sql)
        conn.commit()

    if seed_fn:
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        if row_count == 0:
            seed_fn(conn)
            conn.commit()


def init_database() -> None:
    """Create/repair every table and seed defaults. Safe to call on every
    script rerun -- only acts when a table is missing, malformed, or empty."""
    with closing(get_connection()) as conn:
        _ensure_table(
            conn, "departments", DEPARTMENTS_COLUMNS,
            """
            CREATE TABLE departments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                department_name TEXT NOT NULL UNIQUE
            )
            """,
            seed_fn=lambda c: c.executemany(
                "INSERT OR IGNORE INTO departments (department_name) VALUES (?)",
                [(d,) for d in DEFAULT_DEPARTMENTS],
            ),
        )
        _ensure_table(
            conn, "sessions", SESSIONS_COLUMNS,
            """
            CREATE TABLE sessions (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                session TEXT NOT NULL UNIQUE
            )
            """,
            seed_fn=lambda c: c.executemany(
                "INSERT OR IGNORE INTO sessions (session) VALUES (?)",
                [(s,) for s in DEFAULT_SESSIONS],
            ),
        )
        _ensure_table(
            conn, "teachers", TEACHERS_COLUMNS,
            """
            CREATE TABLE teachers (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_name TEXT NOT NULL,
                department   TEXT NOT NULL,
                designation  TEXT NOT NULL
            )
            """,
            seed_fn=lambda c: c.executemany(
                "INSERT INTO teachers (teacher_name, department, designation) VALUES (?, ?, ?)",
                SAMPLE_TEACHERS,
            ),
        )
        _ensure_table(
            conn, "timetable", TIMETABLE_COLUMNS,
            """
            CREATE TABLE timetable (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                department TEXT NOT NULL,
                session    TEXT NOT NULL,
                section    TEXT NOT NULL,
                day        TEXT NOT NULL,
                subject    TEXT NOT NULL,
                teacher    TEXT NOT NULL,
                room       TEXT NOT NULL,
                time       TEXT NOT NULL
            )
            """,
            seed_fn=lambda c: c.executemany(
                """
                INSERT INTO timetable (department, session, section, day, subject, teacher, room, time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                SAMPLE_TIMETABLE,
            ),
        )


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
def get_departments() -> list:
    with closing(get_connection()) as conn:
        rows = conn.execute("SELECT department_name FROM departments ORDER BY department_name").fetchall()
    return [r[0] for r in rows]


def add_department(name: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute("INSERT OR IGNORE INTO departments (department_name) VALUES (?)", (name,))
        conn.commit()


def rename_department(old_name: str, new_name: str) -> None:
    """Rename a department and cascade the change into teachers/timetable so
    existing records stay in sync instead of silently becoming orphaned."""
    with closing(get_connection()) as conn:
        conn.execute("UPDATE departments SET department_name=? WHERE department_name=?", (new_name, old_name))
        conn.execute("UPDATE teachers SET department=? WHERE department=?", (new_name, old_name))
        conn.execute("UPDATE timetable SET department=? WHERE department=?", (new_name, old_name))
        conn.commit()


def delete_department(name: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM departments WHERE department_name=?", (name,))
        conn.commit()


def count_department_usage(name: str) -> dict:
    """Teachers/timetable rows still referencing this department -- shown to
    the admin before deleting, so data loss is never silent."""
    with closing(get_connection()) as conn:
        teachers = conn.execute("SELECT COUNT(*) FROM teachers WHERE department=?", (name,)).fetchone()[0]
        entries = conn.execute("SELECT COUNT(*) FROM timetable WHERE department=?", (name,)).fetchone()[0]
    return {"teachers": teachers, "timetable_entries": entries}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def get_sessions() -> list:
    with closing(get_connection()) as conn:
        rows = conn.execute("SELECT session FROM sessions").fetchall()
    values = [r[0] for r in rows]
    try:
        return sorted(values, key=int)
    except ValueError:
        return sorted(values)


def add_session(session: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute("INSERT OR IGNORE INTO sessions (session) VALUES (?)", (session,))
        conn.commit()


def rename_session(old_session: str, new_session: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute("UPDATE sessions SET session=? WHERE session=?", (new_session, old_session))
        conn.execute("UPDATE timetable SET session=? WHERE session=?", (new_session, old_session))
        conn.commit()


def delete_session(session: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM sessions WHERE session=?", (session,))
        conn.commit()


def count_session_usage(session: str) -> int:
    with closing(get_connection()) as conn:
        return conn.execute("SELECT COUNT(*) FROM timetable WHERE session=?", (session,)).fetchone()[0]


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------
def get_teachers() -> pd.DataFrame:
    with closing(get_connection()) as conn:
        return pd.read_sql_query("SELECT * FROM teachers ORDER BY teacher_name", conn)


def get_teacher_names() -> list:
    with closing(get_connection()) as conn:
        rows = conn.execute("SELECT teacher_name FROM teachers ORDER BY teacher_name").fetchall()
    return [r[0] for r in rows]


def add_teacher(teacher_name: str, department: str, designation: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            "INSERT INTO teachers (teacher_name, department, designation) VALUES (?, ?, ?)",
            (teacher_name, department, designation),
        )
        conn.commit()


def update_teacher(teacher_id: int, teacher_name: str, department: str, designation: str) -> None:
    with closing(get_connection()) as conn:
        old_row = conn.execute("SELECT teacher_name FROM teachers WHERE id=?", (teacher_id,)).fetchone()
        conn.execute(
            "UPDATE teachers SET teacher_name=?, department=?, designation=? WHERE id=?",
            (teacher_name, department, designation, teacher_id),
        )
        # Keep timetable rows in sync if the teacher's name changed.
        if old_row and old_row[0] != teacher_name:
            conn.execute("UPDATE timetable SET teacher=? WHERE teacher=?", (teacher_name, old_row[0]))
        conn.commit()


def delete_teacher(teacher_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
        conn.commit()


def count_teacher_usage(teacher_name: str) -> int:
    with closing(get_connection()) as conn:
        return conn.execute("SELECT COUNT(*) FROM timetable WHERE teacher=?", (teacher_name,)).fetchone()[0]


# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------
def fetch_all_timetable() -> pd.DataFrame:
    with closing(get_connection()) as conn:
        return pd.read_sql_query("SELECT * FROM timetable", conn)


def query_public_timetable(department: str, session: str, section: str, day: str) -> list:
    """Rows for the student view -- subject/teacher/room/time only, always
    sorted by class time."""
    with closing(get_connection()) as conn:
        return conn.execute(
            """
            SELECT subject, teacher, room, time FROM timetable
            WHERE department=? AND session=? AND section=? AND day=?
            ORDER BY time
            """,
            (department, session, section, day),
        ).fetchall()


def _sorted_by_time(df: pd.DataFrame) -> pd.DataFrame:
    """Sort chronologically by the start of the 'HH:MM-HH:MM' time string
    (so '09:00' sorts before '10:00', unlike plain alphabetical sort)."""
    if df.empty:
        return df
    starts = df["time"].apply(lambda t: parse_time_range(t)[0] or 0)
    return df.assign(_start=starts).sort_values(["day", "_start"]).drop(columns="_start").reset_index(drop=True)


def get_timetable_entry(entry_id: int) -> Optional[dict]:
    with closing(get_connection()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM timetable WHERE id=?", (entry_id,)).fetchone()
    return dict(row) if row else None


def search_timetable(keyword: str) -> pd.DataFrame:
    """Case-insensitive search across subject, teacher, room, department,
    session, section, and day."""
    like = f"%{keyword}%"
    with closing(get_connection()) as conn:
        df = pd.read_sql_query(
            """
            SELECT * FROM timetable
            WHERE subject LIKE ? OR teacher LIKE ? OR room LIKE ? OR department LIKE ?
               OR session LIKE ? OR section LIKE ? OR day LIKE ?
            """,
            conn,
            params=[like] * 7,
        )
    return _sorted_by_time(df)


def filter_timetable(department="All", session="All", section="All", day="All", teacher="All") -> pd.DataFrame:
    query = "SELECT * FROM timetable WHERE 1=1"
    params = []
    for col, val in [
        ("department", department), ("session", session), ("section", section),
        ("day", day), ("teacher", teacher),
    ]:
        if val and val != "All":
            query += f" AND {col} = ?"
            params.append(val)
    with closing(get_connection()) as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return _sorted_by_time(df)


def check_conflicts(department, session, section, day, time, room, teacher,
                     exclude_id: Optional[int] = None) -> Optional[str]:
    """Validate a (possibly edited) timetable slot against every other row on
    the same day. Returns a human-readable error message, or None if clear.

    Checked in priority order so the most specific problem is reported first:
      1. the same class (department+session+section) already has a slot that
         overlaps this time  -> "A timetable already exists for this class."
      2. the room is booked elsewhere at an overlapping time
         -> "Room already booked for this time."
      3. the teacher is teaching elsewhere at an overlapping time
         -> "Teacher already has another class during this time."
    """
    target_range = parse_time_range(time)
    if target_range == (None, None):
        return "Invalid time format."

    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT id, department, session, section, room, teacher, time FROM timetable WHERE day=?",
            (day,),
        ).fetchall()

    overlapping = []
    for row_id, r_dept, r_sess, r_sec, r_room, r_teacher, r_time in rows:
        if exclude_id is not None and row_id == exclude_id:
            continue
        if time_ranges_overlap(target_range, parse_time_range(r_time)):
            overlapping.append(
                {"department": r_dept, "session": r_sess, "section": r_sec, "room": r_room, "teacher": r_teacher}
            )

    for r in overlapping:
        if r["department"] == department and r["session"] == session and r["section"] == section:
            return "A timetable already exists for this class."
    for r in overlapping:
        if r["room"] == room:
            return "Room already booked for this time."
    for r in overlapping:
        if r["teacher"] == teacher:
            return "Teacher already has another class during this time."
    return None


def add_timetable_entry(department, session, section, day, subject, teacher, room, time) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            """
            INSERT INTO timetable (department, session, section, day, subject, teacher, room, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (department, session, section, day, subject, teacher, room, time),
        )
        conn.commit()


def update_timetable_entry(entry_id, department, session, section, day, subject, teacher, room, time) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            """
            UPDATE timetable
            SET department=?, session=?, section=?, day=?, subject=?, teacher=?, room=?, time=?
            WHERE id=?
            """,
            (department, session, section, day, subject, teacher, room, time, entry_id),
        )
        conn.commit()


def delete_timetable_entry(entry_id) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM timetable WHERE id=?", (entry_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Bulk CSV import
# ---------------------------------------------------------------------------
def import_timetable_csv(df: pd.DataFrame) -> list:
    """Bulk-add timetable entries from a DataFrame parsed out of an admin-
    uploaded CSV, so the admin can skip filling the Add Timetable form one
    row at a time.

    Expected columns (any order, extra columns are ignored):
        department, session, section, day, subject, teacher, room, time

    Each row gets almost the same checks as a manual Add Timetable submit,
    with one deliberate difference: an unknown department, session, or
    teacher no longer skips the row. Instead it's auto-created first (the
    teacher gets designation "Lecturer" and is filed under the row's own
    department), and the row continues through the remaining checks --
    section/day must be one of the fixed options, time must be a valid
    'HH:MM-HH:MM' range, and the slot must be conflict-free. Valid rows are
    inserted one at a time (not batched) so that two rows in the same file
    that clash with *each other* are correctly caught too -- the second row
    will see the first one already sitting in the table when it's checked.

    Raises ValueError if the file is missing a required column outright.
    Returns a list of dicts, one per input row, each with the original
    field values plus 'row' (1-based, matching the CSV including its header
    so it lines up with what the admin sees in a spreadsheet), 'status'
    ("Added" or "Skipped"), and 'reason' (empty string when Added, and
    noting any auto-created department/session/teacher when Added).
    """
    missing = [c for c in TIMETABLE_IMPORT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required column(s): {', '.join(missing)}")

    valid_departments = set(get_departments())
    valid_sessions = set(get_sessions())
    valid_teachers = set(get_teacher_names())

    results = []
    for idx, row in df.iterrows():
        row_num = idx + 2  # +1 for 0-index, +1 to account for the header row

        department = str(row.get("department", "") or "").strip()
        session_val = str(row.get("session", "") or "").strip()
        section = str(row.get("section", "") or "").strip()
        day = str(row.get("day", "") or "").strip()
        subject = str(row.get("subject", "") or "").strip()
        teacher = str(row.get("teacher", "") or "").strip()
        room = str(row.get("room", "") or "").strip()
        time_val = str(row.get("time", "") or "").strip()

        entry = {
            "row": row_num, "department": department, "session": session_val, "section": section,
            "day": day, "subject": subject, "teacher": teacher, "room": room, "time": time_val,
        }

        def _skip(reason: str) -> None:
            entry["status"] = "Skipped"
            entry["reason"] = reason
            results.append(entry)

        if not validate_non_empty(department, session_val, section, day, subject, teacher, room, time_val):
            _skip("One or more required fields are empty.")
            continue

        auto_created = []

        # Auto-create missing department/session/teacher before any further
        # validation -- each insert is committed immediately, so it's
        # visible to check_conflicts() and to later rows in this same file.
        if department not in valid_departments:
            add_department(department)
            valid_departments.add(department)
            auto_created.append(f"department '{department}'")
        if session_val not in valid_sessions:
            add_session(session_val)
            valid_sessions.add(session_val)
            auto_created.append(f"session '{session_val}'")
        if teacher not in valid_teachers:
            add_teacher(teacher, department, "Lecturer")
            valid_teachers.add(teacher)
            auto_created.append(f"teacher '{teacher}' (Lecturer)")

        if section not in SECTION_OPTIONS:
            _skip(f"Section must be one of {SECTION_OPTIONS}.")
            continue
        if day not in DAY_ORDER:
            _skip(f"Day must be one of {DAY_ORDER}.")
            continue
        if not validate_time_format(time_val):
            _skip("Time must look like HH:MM-HH:MM (24-hour), start before end -- e.g. 08:30-09:50.")
            continue

        conflict = check_conflicts(department, session_val, section, day, time_val, room, teacher)
        if conflict:
            _skip(conflict)
            continue

        try:
            add_timetable_entry(department, session_val, section, day, subject, teacher, room, time_val)
            entry["status"] = "Added"
            entry["reason"] = ("Auto-created " + ", ".join(auto_created) + ".") if auto_created else ""
            results.append(entry)
        except sqlite3.Error as exc:
            _skip(f"Database error: {exc}")

    return results


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------
def get_dashboard_stats() -> dict:
    today_name = datetime.now().strftime("%A")
    with closing(get_connection()) as conn:
        departments = conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        teachers = conn.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
        entries = conn.execute("SELECT COUNT(*) FROM timetable").fetchone()[0]
        today_classes = conn.execute("SELECT COUNT(*) FROM timetable WHERE day=?", (today_name,)).fetchone()[0]
    return {
        "departments": departments,
        "sessions": sessions,
        "teachers": teachers,
        "timetable_entries": entries,
        "today_classes": today_classes,
        "today_name": today_name,
    }