from fpdf import FPDF

from app.schemas.publishing import TeacherKnowledgePackage

# fpdf2's built-in Helvetica font only supports latin-1. LLM output routinely
# uses "smart" typographic punctuation outside that range; map the common
# ones to ASCII and fall back to dropping anything else rather than crashing.
_UNICODE_TO_ASCII = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...",
})


def _sanitize_for_pdf(text: str) -> str:
    ascii_ish = text.translate(_UNICODE_TO_ASCII)
    return ascii_ish.encode("latin-1", errors="replace").decode("latin-1")


def _multi_cell(pdf: FPDF, h: int, text: str) -> None:
    """Wrap multi_cell to reset cursor to left margin before rendering.

    Fixes fpdf2 quirk: after multi_cell() call, pdf.x remains at right margin.
    Without reset, subsequent multi_cell() calls compute zero/negative available width.
    """
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, h, _sanitize_for_pdf(text))


def _new_pdf(title: str, tkp: TeacherKnowledgePackage) -> FPDF:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    _multi_cell(pdf, 10, title)
    pdf.set_font("Helvetica", "", 11)
    _multi_cell(pdf, 8, f"{tkp.classification.subject} | Grade {tkp.classification.grade} | "
                        f"{tkp.classification.chapter}")
    pdf.ln(4)
    return pdf


def _heading(pdf: FPDF, text: str) -> None:
    pdf.set_font("Helvetica", "B", 13)
    _multi_cell(pdf, 8, text)
    pdf.set_font("Helvetica", "", 11)


def render_lesson_plan_pdf(tkp: TeacherKnowledgePackage) -> bytes:
    pdf = _new_pdf("Lesson Plan", tkp)
    for package in tkp.teaching_plan.periods:
        period = package.plan
        _heading(pdf, f"Period {period.period_no}: {period.title} ({period.duration_min} min)")
        _multi_cell(pdf, 7, "Objectives: " + "; ".join(period.objectives))
        _multi_cell(pdf, 7, "Concepts covered: " + "; ".join(period.concepts_covered))
        _multi_cell(pdf, 7, "Sequencing notes: " + period.sequencing_notes)
        pdf.ln(4)
    return bytes(pdf.output())


def render_teacher_guide_pdf(tkp: TeacherKnowledgePackage) -> bytes:
    pdf = _new_pdf("Teacher Guide", tkp)
    for package in tkp.teaching_plan.periods:
        period, content = package.plan, package.content
        _heading(pdf, f"Period {period.period_no}: {period.title}")
        _multi_cell(pdf, 7, "Entry Ticket: " + content.entry_ticket)
        _multi_cell(pdf, 7, "Teacher Script: " + content.teacher_script)
        _multi_cell(pdf, 7, "Blackboard Notes: " + content.blackboard_notes)
        for activity in package.activities:
            _multi_cell(pdf, 7, f"Activity ({activity.type}, {activity.duration_min} min): "
                                f"{activity.teacher_instructions}")
        _multi_cell(pdf, 7, "Exit Ticket: " + content.exit_ticket)
        _multi_cell(pdf, 7, "Homework: " + content.homework)
        _multi_cell(pdf, 7, "Mentor Moment: " + content.mentor_moment)
        pdf.ln(4)
    return bytes(pdf.output())


def render_assessment_book_pdf(tkp: TeacherKnowledgePackage) -> bytes:
    pdf = _new_pdf("Assessment Book", tkp)
    for package in tkp.teaching_plan.periods:
        period, assessment = package.plan, package.assessment
        _heading(pdf, f"Period {period.period_no}: {period.title}")
        _multi_cell(pdf, 7, "MCQs: " + "; ".join(assessment.mcqs))
        _multi_cell(pdf, 7, "Short Answer: " + "; ".join(assessment.short_answer))
        _multi_cell(pdf, 7, "Long Answer: " + "; ".join(assessment.long_answer))
        _multi_cell(pdf, 7, "Numerical: " + "; ".join(assessment.numerical))
        _multi_cell(pdf, 7, "Answer Key: " + assessment.answer_key)
        _multi_cell(pdf, 7, "Rubric: " + assessment.rubric)
        pdf.ln(4)
    return bytes(pdf.output())
