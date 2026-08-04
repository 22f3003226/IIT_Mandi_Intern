import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from app.jobs.manager import JobManager
from app.jobs.pipeline import run_pipeline
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract


def make_classification():
    return ClassificationResult(
        subject="Physics", grade="9", difficulty="medium", topic="Motion",
        chapter="Laws of Motion", category="STEM", language="English",
    )


def make_extraction():
    return KnowledgeExtract(
        learning_objectives=[], prerequisites=[], concepts=[], definitions=[],
        formulae=[], keywords=[], examples=[], applications=[], misconceptions=[],
    )


def test_run_pipeline_completes_job_and_writes_result(tmp_path, sample_txt):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path=str(sample_txt))
    storage_dir = str(tmp_path / "files")

    with patch("app.jobs.pipeline.classify", return_value=make_classification()), \
         patch("app.jobs.pipeline.extract", return_value=make_extraction()):
        asyncio.run(run_pipeline(manager, storage_dir, job_id, str(sample_txt)))

    job = manager.get_job(job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 100
    result_path = Path(job["result_path"])
    assert result_path.exists()
    data = json.loads(result_path.read_text())
    assert data["classification"]["subject"] == "Physics"


def test_run_pipeline_marks_job_failed_on_parser_error(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    bad_path = str(tmp_path / "missing.txt")
    job_id = manager.create_job(file_path=bad_path)
    storage_dir = str(tmp_path / "files")

    asyncio.run(run_pipeline(manager, storage_dir, job_id, bad_path))

    job = manager.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error"]
