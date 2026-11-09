from pathlib import Path

from fpdf import FPDF

from app.models import Consultation, ConsultationReport, Patient

_FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSansDevanagari-Regular.ttf"
_FONT = "Noto"

# Core (base-14) fonts always carry Latin glyphs; Noto Sans Devanagari does not.
_LATIN_FONT = "helvetica"

_SECTION_LABELS = [
    ("chief_complaint", "Chief Complaint"),
    ("symptoms", "Symptoms"),
    ("medical_history", "Medical History"),
    ("clinical_observations", "Clinical Observations"),
    ("diagnosis", "Diagnosis"),
    ("investigations", "Investigations"),
    ("treatment_and_advice", "Treatment and Advice"),
    ("follow_up", "Follow-up"),
    ("unclear_or_missing", "Unclear / Missing Information"),
]

_MED_FIELDS = [("name", "Name"), ("dosage", "Dosage"), ("frequency", "Frequency"), ("duration", "Duration")]


def _fmt(value):
    if isinstance(value, list):
        return "\n".join(str(v) for v in value if v is not None) or "-"
    if value is None:
        return "-"
    return str(value)


def _is_deva(ch):
    return ord(ch) > 0xFF


def _script_runs(text):
    runs = []
    cur_type = None
    cur = []
    for ch in text:
        t = "deva" if _is_deva(ch) else "latin"
        if t != cur_type:
            if cur:
                runs.append((cur_type, "".join(cur)))
            cur_type = t
            cur = [ch]
        else:
            cur.append(ch)
    if cur:
        runs.append((cur_type, "".join(cur)))
    return runs or [("latin", "")]


def _set_segment_font(pdf, seg_type, style, size):
    if seg_type == "deva":
        pdf.set_font(_FONT, style, size)
    else:
        pdf.set_font(_LATIN_FONT, style, size)


def _content_line(pdf, text, size, style=""):
    if text == "":
        text = "-"
    for seg_type, seg in _script_runs(text):
        _set_segment_font(pdf, seg_type, style, size)
        pdf.write(size, seg)
    pdf.ln(size + 1)


def _heading(pdf, label, size=11):
    _content_line(pdf, label, size, "B")


def build_report_pdf(report: ConsultationReport, patient: Patient | None, consultation: Consultation) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    for style in ("", "B", "I"):
        pdf.add_font(_FONT, style, _FONT_PATH)

    _content_line(pdf, "DoctorDoc Consultation Report", 16, "B")
    pdf.ln(2)

    if patient:
        _content_line(pdf, f"Patient: {patient.full_name or '—'}", 10)
        _content_line(pdf, f"Mobile: {patient.mobile or '—'}", 10)
    date = consultation.started_at.isoformat() if consultation.started_at else None
    _content_line(pdf, f"Consultation date: {date or '-'}", 10)
    pdf.ln(2)

    data = report.structured_report or {}
    for key, label in _SECTION_LABELS:
        _heading(pdf, label)
        for line in _fmt(data.get(key)).split("\n"):
            _content_line(pdf, line, 10)
        pdf.ln(2)

    _heading(pdf, "Medications")
    meds = data.get("medications") or []
    if not meds:
        _content_line(pdf, "-", 10)
    for med in meds:
        if not isinstance(med, dict):
            continue
        parts = [_fmt(med.get(key)) for key, _ in _MED_FIELDS]
        _content_line(pdf, " · ".join(parts), 10)
    pdf.ln(3)

    if report.status == "approved":
        approved_by = f"user #{report.approved_by}" if report.approved_by else "doctor"
        approved_at = report.approved_at.isoformat() if report.approved_at else "-"
        _content_line(pdf, f"Approved by {approved_by} on {approved_at}", 10, "B")

    pdf.ln(4)
    _content_line(pdf, "AI-generated draft. The doctor must review before use for medical documentation.", 8, "I")
    return bytes(pdf.output())