from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.main import app


def test_upload_document_creates_job(tmp_path, monkeypatch, sample_txt):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))

    with patch("app.api.documents.run_pipeline", new=AsyncMock()):
        client = TestClient(app)
        with open(sample_txt, "rb") as f:
            response = client.post("/documents", files={"file": ("sample.txt", f, "text/plain")})

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    assert deps.job_manager.get_job(job_id) is not None


def test_upload_document_rejects_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    client = TestClient(app)
    response = client.post("/documents", files={"file": ("notes.xyz", b"hello", "text/plain")})
    assert response.status_code == 400


def test_upload_document_contains_traversal_filename_within_storage_dir(tmp_path, monkeypatch):
    storage_dir = tmp_path / "files"
    monkeypatch.setattr(settings, "storage_dir", str(storage_dir))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))

    with patch("app.api.documents.run_pipeline", new=AsyncMock()):
        client = TestClient(app)
        response = client.post(
            "/documents", files={"file": ("../../evil.txt", b"hello", "text/plain")}
        )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    job = deps.job_manager.get_job(job_id)
    written_path = Path(job["file_path"]).resolve()
    assert storage_dir.resolve() in written_path.parents
