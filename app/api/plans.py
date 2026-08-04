import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app import deps
from app.config import settings
from app.jobs.pipeline_plan import run_plan_pipeline
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.job import JobStatusResponse

router = APIRouter()

_background_tasks: set[asyncio.Task] = set()


def _to_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        id=job["id"], status=job["status"], stage=job["stage"],
        progress=job["progress"], error=job["error"], result_path=job["result_path"],
    )


@router.post("/jobs/{job_id}/plan", response_model=JobStatusResponse)
async def create_plan(job_id: str) -> JobStatusResponse:
    source_job = deps.job_manager.get_job(job_id)
    if source_job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if source_job["job_type"] != "document":
        raise HTTPException(status_code=400, detail="Source job is not a document job")
    if source_job["status"] != "completed" or not source_job["result_path"]:
        raise HTTPException(status_code=400, detail="Source job result not available")

    try:
        raw = await asyncio.to_thread(Path(source_job["result_path"]).read_text)
        source = DocumentKnowledgeExtract.model_validate(json.loads(raw))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Source job result is unreadable or invalid") from exc

    plan_job_id = deps.job_manager.create_job(
        file_path=source_job["file_path"], job_type="plan", parent_job_id=job_id
    )
    task = asyncio.create_task(
        run_plan_pipeline(deps.job_manager, settings.storage_dir, plan_job_id, source, job_id)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return _to_response(deps.job_manager.get_job(plan_job_id))


@router.get("/jobs/{job_id}/plan")
async def get_plan(job_id: str):
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["job_type"] != "plan":
        raise HTTPException(status_code=400, detail="Job is not a plan job")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Plan job is not completed")
    raw = await asyncio.to_thread(Path(job["result_path"]).read_text)
    return json.loads(raw)
