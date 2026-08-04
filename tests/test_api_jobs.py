from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.main import app


def test_get_job_returns_status(tmp_path):
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.txt")

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_get_job_returns_404_for_unknown(tmp_path):
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    client = TestClient(app)
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404


def test_get_job_result_returns_saved_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    result_path = tmp_path / "DocumentKnowledgeExtract.json"
    result_path.write_text('{"hello": "world"}')
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(job_id, status="completed", result_path=str(result_path))

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}/result")
    assert response.status_code == 200
    assert response.json() == {"hello": "world"}


def test_get_job_result_400_when_not_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}/result")
    assert response.status_code == 400
