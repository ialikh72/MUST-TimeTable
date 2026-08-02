"""
utils.py
========
Validation, time-overlap helpers, and export (CSV/Excel/PDF) utilities for
the MUST Timetable Management System.

Deliberately has no Streamlit or database imports -- this module is pure
logic, easy to unit test in isolation and reused by both database.py
(conflict checks) and main.py (form validation, export buttons).
"""

import io
import re
from typing import Optional, Tuple

import pandas as pd

# Matches "HH:MM-HH:MM" in 24-hour time, e.g. "08:30-09:50"
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_non_empty(*values: str) -> bool:
    """True only if every given value is a non-blank string."""
    return all(isinstance(v, str) and v.strip() for v in values)


def parse_time_range(time_str: str) -> Tuple[Optional[int], Optional[int]]:
    """Convert 'HH:MM-HH:MM' into (start_minutes, end_minutes) since
    midnight. Returns (None, None) if the string doesn't match the format."""
    match = TIME_PATTERN.match((time_str or "").strip())
    if not match:
        return None, None
    start_h, start_m, end_h, end_m = (int(g) for g in match.groups())
    return start_h * 60 + start_m, end_h * 60 + end_m


def validate_time_format(time_str: str) -> bool:
    """Check the string is a well-formed 'HH:MM-HH:MM' range with start
    strictly before end (rejects e.g. '10:00-09:00')."""
    start, end = parse_time_range(time_str)
    return start is not None and end is not None and start < end


def time_ranges_overlap(range_a: Tuple[Optional[int], Optional[int]],
                         range_b: Tuple[Optional[int], Optional[int]]) -> bool:
    """True if two (start_minutes, end_minutes) ranges overlap at all."""
    a_start, a_end = range_a
    b_start, b_end = range_b
    if None in (a_start, a_end, b_start, b_end):
        return False
    return a_start < b_end and b_start < a_end


# ---------------------------------------------------------------------------
# Export helpers -- each returns raw bytes ready for st.download_button.
# export_to_pdf returns None (instead of raising) if reportlab is missing,
# so the caller can show a friendly message instead of crashing.
# ---------------------------------------------------------------------------
def export_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def export_to_excel(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Timetable")
    return buffer.getvalue()


def export_to_pdf(df: pd.DataFrame, title: str = "MUST Timetable") -> Optional[bytes]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    data = [list(df.columns)] + df.astype(str).values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0c419")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    return buffer.getvalue()