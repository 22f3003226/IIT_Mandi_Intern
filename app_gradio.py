"""Gradio demo entry point for Hugging Face Spaces.

Runs the same ten-stage pipeline as the FastAPI app (see app/jobs/pipeline*.py
for the async, job-queue version used in production/local API mode), but
synchronously and in-process, since a Gradio Space just needs a single
request/response demo, not a background job queue with SSE streaming.
"""

import json
import tempfile
from pathlib import Path

import gradio as gr

from app.activities.generate import generate_activities
from app.assessment.generate import generate_assessment
from app.classification.classify import classify
from app.content.generate import generate_content
from app.extraction.extract import extract
from app.gaps.generate import generate_gaps
from app.parsers.router import route_and_parse
from app.planning.plan import plan_periods
from app.publishing.assemble import assemble_tkp
from app.publishing.pdf import render_assessment_book_pdf, render_lesson_plan_pdf, render_teacher_guide_pdf
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.planning import PeriodPackage
from app.validation.validate import validate

try:
    import spaces

    @spaces.GPU
    def _zerogpu_startup_probe() -> None:
        """Unused. HF's ZeroGPU hardware refuses to boot a Space with zero
        @spaces.GPU-decorated functions, even though this app never needs a
        GPU (every stage here is a plain OpenRouter API call). Satisfies that
        startup check without ever being called."""
        return None

except ImportError:
    pass  # `spaces` is only present inside a Hugging Face Space runtime

DOC_NATURE_HINTS = [
    "Not Sure",
    "Mostly Text",
    "Text with Tables",
    "Text with Diagrams/Figures",
    "Text with Equations",
    "Scanned PDF",
]


def run_pipeline(file_path: str, doc_nature_hint: str, progress: gr.Progress):
    progress(0.05, desc="Parsing document")
    parsed = route_and_parse(file_path, None if doc_nature_hint == "Not Sure" else doc_nature_hint)

    progress(0.15, desc="Classifying document")
    classification = classify(parsed)

    progress(0.25, desc="Extracting knowledge")
    knowledge = extract(parsed, classification)

    progress(0.35, desc="Planning teaching periods")
    skeleton = plan_periods(knowledge, classification)
    if not skeleton.periods:
        raise gr.Error("Teaching planner returned no periods for this document.")

    packages: list[PeriodPackage] = []
    num_periods = len(skeleton.periods)
    for index, period in enumerate(skeleton.periods):
        base = 0.35 + 0.4 * (index / num_periods)
        progress(base, desc=f"Generating content for period {period.period_no}")
        content = generate_content(period, knowledge, classification)
        activities = generate_activities(period, classification, content)
        assessment = generate_assessment(period, classification, content)
        packages.append(PeriodPackage(plan=period, content=content, activities=activities, assessment=assessment))

    progress(0.78, desc="Analyzing learning gaps")
    gap_analysis = generate_gaps(knowledge, packages)

    from app.schemas.planning import TeachingPlan

    plan = TeachingPlan(job_id="gradio-demo", source_job_id="gradio-demo", periods=packages, gap_analysis=gap_analysis)

    progress(0.88, desc="Validating generated plan")
    report = validate(plan, knowledge)

    progress(0.94, desc="Assembling Teacher Knowledge Package")
    source = DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)
    tkp = assemble_tkp(
        job_id="gradio-demo", source_job_id="gradio-demo", plan_job_id="gradio-demo",
        source=source, plan=plan, validation_report=report,
    )

    progress(0.97, desc="Rendering PDFs")
    out_dir = Path(tempfile.mkdtemp(prefix="tkp-"))
    tkp_path = out_dir / "TeacherKnowledgePackage.json"
    tkp_path.write_text(tkp.model_dump_json(indent=2), encoding="utf-8")

    lesson_plan_path = out_dir / "lesson-plan.pdf"
    lesson_plan_path.write_bytes(render_lesson_plan_pdf(tkp))
    teacher_guide_path = out_dir / "teacher-guide.pdf"
    teacher_guide_path.write_bytes(render_teacher_guide_pdf(tkp))
    assessment_book_path = out_dir / "assessment-book.pdf"
    assessment_book_path.write_bytes(render_assessment_book_pdf(tkp))

    progress(1.0, desc="Done")

    summary = {
        "classification": classification.model_dump(),
        "num_periods": num_periods,
        "validation_report": report.model_dump(),
    }
    return (
        json.dumps(summary, indent=2),
        str(tkp_path),
        str(lesson_plan_path),
        str(teacher_guide_path),
        str(assessment_book_path),
    )


def handle_upload(file, doc_nature_hint, progress=gr.Progress()):
    if file is None:
        raise gr.Error("Upload a document first.")
    try:
        return run_pipeline(file, doc_nature_hint, progress)
    except gr.Error:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the UI
        raise gr.Error(f"Pipeline failed: {exc}") from exc


CSS = """
html, body, #root, .gradio-container, .app {
    height: auto !important;
    overflow-y: auto !important;
}
"""

with gr.Blocks(title="Teacher AI Platform", css=CSS) as demo:
    gr.Markdown(
        "# Teacher AI Platform\n"
        "Upload a chapter (PDF, DOCX, PPTX, or TXT) and get a full Teacher "
        "Knowledge Package: a multi-period teaching plan, classroom content, "
        "activities, assessments, a learning-gap analysis, and a validation "
        "report, plus three ready-to-print PDFs."
    )
    with gr.Row():
        file_input = gr.File(label="Document", file_types=[".pdf", ".docx", ".pptx", ".txt"], type="filepath")
        hint_input = gr.Dropdown(DOC_NATURE_HINTS, value="Not Sure", label="Document nature (optional hint)")
    submit_btn = gr.Button("Generate Teacher Knowledge Package", variant="primary")

    summary_output = gr.Code(label="Summary (classification, periods, validation report)", language="json")
    with gr.Row():
        tkp_output = gr.File(label="TeacherKnowledgePackage.json")
        lesson_plan_output = gr.File(label="Lesson Plan PDF")
        teacher_guide_output = gr.File(label="Teacher Guide PDF")
        assessment_book_output = gr.File(label="Assessment Book PDF")

    submit_btn.click(
        handle_upload,
        inputs=[file_input, hint_input],
        outputs=[summary_output, tkp_output, lesson_plan_output, teacher_guide_output, assessment_book_output],
    )

if __name__ == "__main__":
    demo.launch()
