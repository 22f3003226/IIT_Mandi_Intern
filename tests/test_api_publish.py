import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.main import app

VALID_TKP = {
    "job_id": "pub-1", "source_job_id": "doc-1", "plan_job_id": "plan-1",
    "classification": {"subject": "Physics", "grade": "9", "difficulty": "medium", "topic": "Motion",
                        "chapter": "Laws", "category": "STEM", "language": "English"},
    "knowledge": {k: [] for k in ["learning_objectives", "prerequisites", "concepts", "definitions",
                                   "formulae", "keywords", "examples", "applications", "misconceptions"]},
    "teaching_plan": {"job_id": "plan-1", "source_job_id": "doc-1", "periods": [], "gap_analysis": []},
    "validation_report": {"issues": [], "passed": True},
}


def test_create_publish_404_for_unknown_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    client = TestClient(app)
    response = client.post("/jobs/does-not-exist/publish")
    assert response.status_code == 404


def test_create_publish_400_when_plan_job_not_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)

    client = TestClient(app)
    response = client.post(f"/jobs/{plan_job_id}/publish")
    assert response.status_code == 400


def test_create_publish_400_when_job_is_not_a_plan_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(doc_job_id, status="completed", result_path="/tmp/x.json")

    client = TestClient(app)
    response = client.post(f"/jobs/{doc_job_id}/publish")
    assert response.status_code == 400


def test_create_publish_starts_pipeline_for_completed_plan_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))

    doc_result = tmp_path / "DocumentKnowledgeExtract.json"
    doc_result.write_text(json.dumps({
        "parsed_document": {"metadata": {"source_filename": "x.txt", "format": "txt", "page_count": 1},
                             "sections": [{"heading": "Intro", "text": "Body.", "page": 1}],
                             "tables": [], "figures": [], "equations": []},
        "classification": {"subject": "Physics", "grade": "9", "difficulty": "medium", "topic": "Motion",
                            "chapter": "Laws", "category": "STEM", "language": "English"},
        "knowledge": {k: [] for k in ["learning_objectives", "prerequisites", "concepts", "definitions",
                                       "formulae", "keywords", "examples", "applications", "misconceptions"]},
    }))
    plan_result = tmp_path / "TeachingPlan.json"
    plan_result.write_text(json.dumps({"job_id": "plan-1", "source_job_id": "doc-1", "periods": [],
                                        "gap_analysis": []}))

    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(doc_job_id, status="completed", result_path=str(doc_result))
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)
    deps.job_manager.update_job(plan_job_id, status="completed", result_path=str(plan_result))

    with patch("app.api.publish.run_publish_pipeline", new=AsyncMock()):
        client = TestClient(app)
        response = client.post(f"/jobs/{plan_job_id}/publish")

    assert response.status_code == 200
    publish_job_id = response.json()["id"]
    publish_job = deps.job_manager.get_job(publish_job_id)
    assert publish_job["job_type"] == "publish"
    assert publish_job["parent_job_id"] == plan_job_id


def test_get_publish_returns_tkp_json_when_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    result_path = tmp_path / "TeacherKnowledgePackage.json"
    result_path.write_text(json.dumps(VALID_TKP))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)
    publish_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish",
                                                  parent_job_id=plan_job_id)
    deps.job_manager.update_job(publish_job_id, status="completed", result_path=str(result_path))

    client = TestClient(app)
    response = client.get(f"/jobs/{publish_job_id}/publish")
    assert response.status_code == 200
    assert response.json()["job_id"] == "pub-1"


def test_get_publish_pdf_streams_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_dir = tmp_path / "files" / "pub-1"
    job_dir.mkdir(parents=True)
    pdf_path = job_dir / "lesson-plan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)
    publish_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish",
                                                  parent_job_id=plan_job_id, job_id="pub-1")
    deps.job_manager.update_job(publish_job_id, status="completed", result_path=str(job_dir / "TeacherKnowledgePackage.json"))

    client = TestClient(app)
    response = client.get(f"/jobs/{publish_job_id}/publish/pdf/lesson-plan")
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 fake"


def test_get_publish_pdf_400_for_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)
    publish_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish",
                                                  parent_job_id=plan_job_id)
    deps.job_manager.update_job(publish_job_id, status="completed",
                                 result_path=str(tmp_path / "files" / publish_job_id / "TeacherKnowledgePackage.json"))

    client = TestClient(app)
    response = client.get(f"/jobs/{publish_job_id}/publish/pdf/not-a-kind")
    assert response.status_code == 400
