from pathlib import Path

from fpdf import FPDF

from app.models import Consultation, ConsultationReport, Patient

_FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSansDevanagari-Regular.ttf"
_FONT = "Noto"

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


def build_report_pdf(report: ConsultationReport, patient: Patient | None, consultation: Consultation) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font(_FONT, "", _FONT_PATH)
    pdf.add_font(_FONT, "B", _FONT_PATH)
    pdf.add_font(_FONT, "I", _FONT_PATH)
    pdf.set_font(_FONT, "", 16)
    pdf.cell(0, 10, "DoctorDoc Consultation Report", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font(_FONT, "", 10)
    if patient:
        pdf.cell(0, 6, f"Patient: {patient.full_name or '—'}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Mobile: {patient.mobile or '—'}", new_x="LMARGIN", new_y="NEXT")
    date = consultation.started_at.isoformat() if consultation.started_at else None
    pdf.cell(0, 6, f"Consultation date: {date or '-'}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    data = report.structured_report or {}
    for key, label in _SECTION_LABELS:
        pdf.set_font(_FONT, "B", 11)
        pdf.cell(0, 7, label, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(_FONT, "", 10)
        for line in _fmt(data.get(key)).split("\n"):
            pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    pdf.set_font(_FONT, "B", 11)
    pdf.cell(0, 7, "Medications", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, "", 10)
    meds = data.get("medications") or []
    if not meds:
        pdf.cell(0, 6, "-", new_x="LMARGIN", new_y="NEXT")
    for med in meds:
        parts = [f"{_fmt(med.get(field))}" for _, field in _MED_FIELDS]
        pdf.multi_cell(0, 5, " · ".join(parts), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    if report.status == "approved":
        pdf.set_font(_FONT, "B", 10)
        approved_by = f"user #{report.approved_by}" if report.approved_by else "doctor"
        approved_at = report.approved_at.isoformat() if report.approved_at else "-"
        pdf.cell(0, 6, f"Approved by {approved_by} on {approved_at}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(_FONT, "I", 8)
    pdf.ln(4)
    pdf.cell(
        0, 5,
        "AI-generated draft. The doctor must review before use for medical documentation.",
        new_x="LMARGIN", new_y="NEXT",
    )
    return bytes(pdf.output())
