import asyncio
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app import deps
from app.config import settings
from app.jobs.pipeline import run_pipeline
from app.parsers.router import SUPPORTED_EXTENSIONS
from app.storage.files import save_upload

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Strong references to in-flight pipeline tasks. The event loop only holds a weak
# reference to a task, so without this a running job can be garbage-collected
# mid-pipeline and silently disappear.
_background_tasks: set[asyncio.Task] = set()


@router.post("/documents")
async def upload_document(file: UploadFile = File(...), doc_nature_hint: Optional[str] = Form(None)):
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")

    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds maximum size of {MAX_UPLOAD_BYTES} bytes",
        )

    job_id = str(uuid.uuid4())
    try:
        file_path = await asyncio.to_thread(
            save_upload, settings.storage_dir, job_id, file.filename, file.file
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    deps.job_manager.create_job(file_path=file_path, job_id=job_id)

    task = asyncio.create_task(
        run_pipeline(deps.job_manager, settings.storage_dir, job_id, file_path, doc_nature_hint)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"job_id": job_id}
