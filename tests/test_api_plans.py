import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.main import app


def test_create_plan_404_for_unknown_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    client = TestClient(app)
    response = client.post("/jobs/does-not-exist/plan")
    assert response.status_code == 404


def test_create_plan_400_when_source_job_not_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")  # status defaults to "queued"

    client = TestClient(app)
    response = client.post(f"/jobs/{job_id}/plan")
    assert response.status_code == 400


def test_create_plan_starts_pipeline_for_completed_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))

    result_path = tmp_path / "DocumentKnowledgeExtract.json"
    result_path.write_text(json.dumps({
        "parsed_document": {
            "metadata": {"source_filename": "x.txt", "format": "txt", "page_count": 1},
            "sections": [{"heading": "Intro", "text": "Body.", "page": 1}],
            "tables": [], "figures": [], "equations": [],
        },
        "classification": {"subject": "Physics", "grade": "9", "difficulty": "medium",
                             "topic": "Motion", "chapter": "Laws", "category": "STEM", "language": "English"},
        "knowledge": {k: [] for k in ["learning_objectives", "prerequisites", "concepts", "definitions",
                                        "formulae", "keywords", "examples", "applications", "misconceptions"]},
    }))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(job_id, status="completed", result_path=str(result_path))

    with patch("app.api.plans.run_plan_pipeline", new=AsyncMock()):
        client = TestClient(app)
        response = client.post(f"/jobs/{job_id}/plan")

    assert response.status_code == 200
    plan_job_id = response.json()["id"]
    plan_job = deps.job_manager.get_job(plan_job_id)
    assert plan_job["job_type"] == "plan"
    assert plan_job["parent_job_id"] == job_id


def test_create_plan_400_when_source_job_is_a_plan_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    result_path = tmp_path / "TeachingPlan.json"
    result_path.write_text(json.dumps({"job_id": "j1", "source_job_id": "j0", "periods": [], "gap_analysis": []}))
    parent_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=parent_id)
    deps.job_manager.update_job(plan_job_id, status="completed", result_path=str(result_path))

    client = TestClient(app)
    response = client.post(f"/jobs/{plan_job_id}/plan")
    assert response.status_code == 400


def test_create_plan_400_when_result_path_missing_despite_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(job_id, status="completed")

    client = TestClient(app)
    response = client.post(f"/jobs/{job_id}/plan")
    assert response.status_code == 400


def test_get_plan_400_when_job_is_not_a_plan_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}/plan")
    assert response.status_code == 400


def test_get_plan_returns_teaching_plan_json_when_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    result_path = tmp_path / "TeachingPlan.json"
    result_path.write_text(json.dumps({"job_id": "j1", "source_job_id": "j0", "periods": [], "gap_analysis": []}))
    parent_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=parent_id)
    deps.job_manager.update_job(plan_job_id, status="completed", result_path=str(result_path))

    client = TestClient(app)
    response = client.get(f"/jobs/{plan_job_id}/plan")
    assert response.status_code == 200
    assert response.json()["job_id"] == "j1"
