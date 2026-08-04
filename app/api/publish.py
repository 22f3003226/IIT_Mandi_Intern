import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app import deps
from app.config import settings
from app.jobs.pipeline_publish import run_publish_pipeline
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.job import JobStatusResponse
from app.schemas.planning import TeachingPlan

router = APIRouter()

_background_tasks: set[asyncio.Task] = set()
_PDF_KINDS = {"lesson-plan", "teacher-guide", "assessment-book"}


def _to_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        id=job["id"], status=job["status"], stage=job["stage"],
        progress=job["progress"], error=job["error"], result_path=job["result_path"],
    )


@router.post("/jobs/{plan_job_id}/publish", response_model=JobStatusResponse)
async def create_publish(plan_job_id: str) -> JobStatusResponse:
    plan_job = deps.job_manager.get_job(plan_job_id)
    if plan_job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if plan_job["job_type"] != "plan":
        raise HTTPException(status_code=400, detail="Source job is not a plan job")
    if plan_job["status"] != "completed" or not plan_job["result_path"]:
        raise HTTPException(status_code=400, detail="Plan job result not available")

    source_job = deps.job_manager.get_job(plan_job["parent_job_id"])
    if source_job is None or source_job["status"] != "completed" or not source_job["result_path"]:
        raise HTTPException(status_code=400, detail="Source document job result not available")

    try:
        plan_raw = await asyncio.to_thread(Path(plan_job["result_path"]).read_text)
        plan = TeachingPlan.model_validate(json.loads(plan_raw))
        source_raw = await asyncio.to_thread(Path(source_job["result_path"]).read_text)
        source = DocumentKnowledgeExtract.model_validate(json.loads(source_raw))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Plan or source job result is unreadable or invalid") from exc

    publish_job_id = deps.job_manager.create_job(
        file_path=plan_job["file_path"], job_type="publish", parent_job_id=plan_job_id
    )
    task = asyncio.create_task(
        run_publish_pipeline(deps.job_manager, settings.storage_dir, publish_job_id, source, plan,
                              plan_job_id, source_job["id"])
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return _to_response(deps.job_manager.get_job(publish_job_id))


@router.get("/jobs/{job_id}/publish")
async def get_publish(job_id: str):
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["job_type"] != "publish":
        raise HTTPException(status_code=400, detail="Job is not a publish job")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Publish job is not completed")
    raw = await asyncio.to_thread(Path(job["result_path"]).read_text)
    return json.loads(raw)


@router.get("/jobs/{job_id}/publish/pdf/{kind}")
async def get_publish_pdf(job_id: str, kind: str):
    if kind not in _PDF_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown PDF kind: {kind!r}")
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["job_type"] != "publish":
        raise HTTPException(status_code=400, detail="Job is not a publish job")
    if job["status"] != "completed" or not job["result_path"]:
        raise HTTPException(status_code=400, detail="Publish job is not completed")
    pdf_path = Path(job["result_path"]).parent / f"{kind}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{kind}.pdf")
