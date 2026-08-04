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


@router.post("/documents")
async def upload_document(file: UploadFile = File(...), doc_nature_hint: Optional[str] = Form(None)):
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")

    job_id = str(uuid.uuid4())
    file_path = save_upload(settings.storage_dir, job_id, file.filename, file.file)
    deps.job_manager.create_job(file_path=file_path, job_id=job_id)

    asyncio.create_task(
        run_pipeline(deps.job_manager, settings.storage_dir, job_id, file_path, doc_nature_hint)
    )
    return {"job_id": job_id}
