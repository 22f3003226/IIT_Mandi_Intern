import asyncio
import logging

from app.jobs.manager import JobManager
from app.publishing.assemble import assemble_tkp
from app.publishing.pdf import render_assessment_book_pdf, render_lesson_plan_pdf, render_teacher_guide_pdf
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.planning import TeachingPlan
from app.storage.files import save_publish_pdf, save_publish_result_json
from app.validation.validate import validate

logger = logging.getLogger(__name__)


async def run_publish_pipeline(
    job_manager: JobManager,
    storage_dir: str,
    job_id: str,
    source: DocumentKnowledgeExtract,
    plan: TeachingPlan,
    plan_job_id: str,
    source_job_id: str,
) -> None:
    try:
        job_manager.update_job(job_id, status="running", stage="validation", progress=20)
        report = await asyncio.to_thread(validate, plan, source.knowledge)

        job_manager.update_job(job_id, stage="assembling", progress=50)
        tkp = assemble_tkp(job_id=job_id, source_job_id=source_job_id, plan_job_id=plan_job_id,
                            source=source, plan=plan, validation_report=report)

        job_manager.update_job(job_id, stage="rendering-pdfs", progress=70)
        for kind, renderer in (
            ("lesson-plan", render_lesson_plan_pdf),
            ("teacher-guide", render_teacher_guide_pdf),
            ("assessment-book", render_assessment_book_pdf),
        ):
            pdf_bytes = await asyncio.to_thread(renderer, tkp)
            await asyncio.to_thread(save_publish_pdf, storage_dir, job_id, kind, pdf_bytes)

        job_manager.update_job(job_id, stage="packaging", progress=95)
        result_path = await asyncio.to_thread(
            save_publish_result_json, storage_dir, job_id, tkp.model_dump_json(indent=2)
        )

        job_manager.update_job(job_id, status="completed", stage="done", progress=100, result_path=result_path)
    except Exception as exc:
        logger.exception("Publish pipeline failed for job %s", job_id)
        job_manager.update_job(job_id, status="failed", error=str(exc))
