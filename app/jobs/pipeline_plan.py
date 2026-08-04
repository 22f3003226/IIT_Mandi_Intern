import asyncio
import logging

from app.activities.generate import generate_activities
from app.assessment.generate import generate_assessment
from app.content.generate import generate_content
from app.gaps.generate import generate_gaps
from app.jobs.manager import JobManager
from app.planning.plan import plan_periods
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.planning import PeriodPackage, TeachingPlan
from app.storage.files import save_plan_result_json

logger = logging.getLogger(__name__)


async def run_plan_pipeline(
    job_manager: JobManager,
    storage_dir: str,
    job_id: str,
    source: DocumentKnowledgeExtract,
    source_job_id: str,
) -> None:
    try:
        job_manager.update_job(job_id, status="running", stage="planning", progress=10)
        skeleton = await asyncio.to_thread(plan_periods, source.knowledge, source.classification)
        if not skeleton.periods:
            raise ValueError("Teaching planner returned no periods")

        num_periods = len(skeleton.periods)
        packages: list[PeriodPackage] = []
        for index, period in enumerate(skeleton.periods):
            base_progress = 10 + int(70 * index / num_periods)
            step_progress = int(70 / num_periods / 3)

            job_manager.update_job(job_id, stage=f"content-period-{period.period_no}", progress=base_progress)
            content = await asyncio.to_thread(generate_content, period, source.knowledge, source.classification)

            job_manager.update_job(
                job_id, stage=f"activities-period-{period.period_no}", progress=base_progress + step_progress
            )
            activities = await asyncio.to_thread(generate_activities, period, source.classification, content)

            job_manager.update_job(
                job_id, stage=f"assessment-period-{period.period_no}", progress=base_progress + 2 * step_progress
            )
            assessment = await asyncio.to_thread(generate_assessment, period, source.classification, content)

            packages.append(PeriodPackage(plan=period, content=content, activities=activities, assessment=assessment))

        job_manager.update_job(job_id, stage="gap-analysis", progress=85)
        gap_analysis = await asyncio.to_thread(generate_gaps, source.knowledge, packages)

        job_manager.update_job(job_id, stage="packaging", progress=95)
        result = TeachingPlan(job_id=job_id, source_job_id=source_job_id, periods=packages, gap_analysis=gap_analysis)
        result_path = await asyncio.to_thread(
            save_plan_result_json, storage_dir, job_id, result.model_dump_json(indent=2)
        )

        job_manager.update_job(job_id, status="completed", stage="done", progress=100, result_path=result_path)
    except Exception as exc:
        logger.exception("Plan pipeline failed for job %s", job_id)
        job_manager.update_job(job_id, status="failed", error=str(exc))
