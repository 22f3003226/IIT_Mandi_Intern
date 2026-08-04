import asyncio
from typing import Optional

from app.classification.classify import classify
from app.extraction.extract import extract
from app.jobs.manager import JobManager
from app.parsers.router import route_and_parse
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.storage.files import save_result_json


async def run_pipeline(
    job_manager: JobManager,
    storage_dir: str,
    job_id: str,
    file_path: str,
    doc_nature_hint: Optional[str] = None,
) -> None:
    try:
        job_manager.update_job(job_id, status="running", stage="parsing", progress=10)
        parsed = await asyncio.to_thread(route_and_parse, file_path, doc_nature_hint)

        job_manager.update_job(job_id, stage="classification", progress=40)
        classification = await asyncio.to_thread(classify, parsed)

        job_manager.update_job(job_id, stage="extraction", progress=70)
        knowledge = await asyncio.to_thread(extract, parsed, classification)

        job_manager.update_job(job_id, stage="packaging", progress=90)
        result = DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)
        result_path = await asyncio.to_thread(
            save_result_json, storage_dir, job_id, result.model_dump_json(indent=2)
        )

        job_manager.update_job(job_id, status="completed", stage="done", progress=100, result_path=result_path)
    except Exception as exc:
        job_manager.update_job(job_id, status="failed", error=str(exc))
