from fastapi.testclient import TestClient

from app import deps
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
