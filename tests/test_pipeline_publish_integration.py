"""End-to-end integration test: document job -> plan job -> publish job.

Exercises the real API endpoints (job creation, chaining, storage) with only
the LLM-calling stage functions mocked, and actually runs each pipeline to
completion (rather than just checking that the API accepted the job).
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.jobs.pipeline_plan import run_plan_pipeline
from app.jobs.pipeline_publish import run_publish_pipeline
from app.main import app
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.planning import Activity, Assessment, GapAnalysisItem, PeriodContent, TeachingPlanSkeleton
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import TeacherKnowledgePackage, ValidationIssue

DOC_KNOWLEDGE_EXTRACT = {
    "parsed_document": {
        "metadata": {"source_filename": "x.txt", "format": "txt", "page_count": 1},
        "sections": [{"heading": "Intro", "text": "Body.", "page": 1}],
        "tables": [], "figures": [], "equations": [],
    },
    "classification": {"subject": "Physics", "grade": "9", "difficulty": "medium",
                        "topic": "Motion", "chapter": "Laws", "category": "STEM", "language": "English"},
    "knowledge": {k: [] for k in ["learning_objectives", "prerequisites", "concepts", "definitions",
                                   "formulae", "keywords", "examples", "applications", "misconceptions"]},
}

PERIOD_SKELETON = {"periods": [
    {"period_no": 1, "duration_min": 40, "title": "Intro to Inertia", "objectives": ["Explain inertia"],
     "concepts_covered": ["Inertia"], "sequencing_notes": "First concept."},
]}
CONTENT_RESPONSE = {
    "entry_ticket": "e", "teacher_script": "s", "blackboard_notes": "b",
    "checkpoint_questions": ["q"], "exit_ticket": "x", "homework": "h", "mentor_moment": "m",
    "grounded_notes": [{"text": "Inertia", "source_ref": {"page": 1, "section": None}}],
}
ACTIVITIES_RESPONSE = [
    {"type": "demo", "duration_min": 10, "materials": ["ball"],
     "teacher_instructions": "roll it", "success_criteria": "predicts motion"}
]
ASSESSMENT_RESPONSE = {"mcqs": ["q"], "short_answer": ["q"], "long_answer": ["q"], "numerical": ["q"],
                        "answer_key": "k", "rubric": "r"}
GAPS_RESPONSE = [
    {"misconception": {"text": "Inertia", "source_ref": {"page": 1, "section": None}},
     "diagnostic_questions": ["q"], "severity": "low", "remedial_action": "a"}
]


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    return TestClient(app)


def _create_completed_document_job(tmp_path):
    result_path = tmp_path / "DocumentKnowledgeExtract.json"
    result_path.write_text(json.dumps(DOC_KNOWLEDGE_EXTRACT))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(doc_job_id, status="completed", result_path=str(result_path))
    return doc_job_id, DocumentKnowledgeExtract.model_validate(DOC_KNOWLEDGE_EXTRACT)


def _run_plan_stage_mocks():
    return (
        patch("app.jobs.pipeline_plan.plan_periods",
              return_value=TeachingPlanSkeleton.model_validate(PERIOD_SKELETON)),
        patch("app.jobs.pipeline_plan.generate_content",
              return_value=PeriodContent.model_validate(CONTENT_RESPONSE)),
        patch("app.jobs.pipeline_plan.generate_activities",
              return_value=[Activity.model_validate(a) for a in ACTIVITIES_RESPONSE]),
        patch("app.jobs.pipeline_plan.generate_assessment",
              return_value=Assessment.model_validate(ASSESSMENT_RESPONSE)),
        patch("app.jobs.pipeline_plan.generate_gaps",
              return_value=[GapAnalysisItem.model_validate(g) for g in GAPS_RESPONSE]),
    )


def _create_and_run_plan_job(client, doc_job_id, source):
    mocks = _run_plan_stage_mocks()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        response = client.post(f"/jobs/{doc_job_id}/plan")
        assert response.status_code == 200
        plan_job_id = response.json()["id"]
        asyncio.run(run_plan_pipeline(deps.job_manager, settings.storage_dir, plan_job_id, source, doc_job_id))
    plan_job = deps.job_manager.get_job(plan_job_id)
    assert plan_job["status"] == "completed"
    plan = TeachingPlan.model_validate(json.loads(Path(plan_job["result_path"]).read_text()))
    return plan_job_id, plan


def test_full_chain_document_to_plan_to_publish_completes_and_writes_all_outputs(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    doc_job_id, source = _create_completed_document_job(tmp_path)
    plan_job_id, plan = _create_and_run_plan_job(client, doc_job_id, source)

    with patch("app.validation.validate.judge_plan", return_value=[]):
        response = client.post(f"/jobs/{plan_job_id}/publish")
        assert response.status_code == 200
        publish_job_id = response.json()["id"]
        asyncio.run(run_publish_pipeline(
            deps.job_manager, settings.storage_dir, publish_job_id, source, plan, plan_job_id, doc_job_id
        ))

    publish_job = deps.job_manager.get_job(publish_job_id)
    assert publish_job["status"] == "completed"

    job_dir = Path(settings.storage_dir) / publish_job_id
    tkp_path = job_dir / "TeacherKnowledgePackage.json"
    assert tkp_path.exists()
    assert (job_dir / "lesson-plan.pdf").exists()
    assert (job_dir / "teacher-guide.pdf").exists()
    assert (job_dir / "assessment-book.pdf").exists()

    tkp = TeacherKnowledgePackage.model_validate(json.loads(tkp_path.read_text()))
    assert tkp.validation_report.passed is True


def test_publish_job_still_completes_when_judge_finds_a_critical_issue(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    doc_job_id, source = _create_completed_document_job(tmp_path)
    plan_job_id, plan = _create_and_run_plan_job(client, doc_job_id, source)

    critical_issue = ValidationIssue(
        severity="critical", category="hallucination", location="period-1",
        description="Fabricated fact not grounded in source.",
    )
    with patch("app.validation.validate.judge_plan", return_value=[critical_issue]):
        response = client.post(f"/jobs/{plan_job_id}/publish")
        assert response.status_code == 200
        publish_job_id = response.json()["id"]
        asyncio.run(run_publish_pipeline(
            deps.job_manager, settings.storage_dir, publish_job_id, source, plan, plan_job_id, doc_job_id
        ))

    publish_job = deps.job_manager.get_job(publish_job_id)
    assert publish_job["status"] == "completed"

    tkp_path = Path(publish_job["result_path"])
    tkp = TeacherKnowledgePackage.model_validate(json.loads(tkp_path.read_text()))
    assert tkp.validation_report.passed is False
