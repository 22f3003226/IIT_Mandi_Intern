import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import deps
from app.schemas.job import JobStatusResponse

router = APIRouter()


def _to_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        id=job["id"], status=job["status"], stage=job["stage"],
        progress=job["progress"], error=job["error"], result_path=job["result_path"],
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_response(job)


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_generator():
        while True:
            job = deps.job_manager.get_job(job_id)
            if job is None:
                yield f"data: {json.dumps({'error': 'not found'})}\n\n"
                return
            payload = {"stage": job["stage"], "progress": job["progress"], "status": job["status"]}
            yield f"data: {json.dumps(payload)}\n\n"
            if job["status"] in ("completed", "failed"):
                return
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
