import asyncio
from unittest.mock import patch

from app.jobs.manager import JobManager
from app.jobs.pipeline_plan import run_plan_pipeline
from app.schemas.classification import ClassificationResult
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section


def _source():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    knowledge = KnowledgeExtract(
        learning_objectives=[item], prerequisites=[item], concepts=[item],
        definitions=[item], formulae=[item], keywords=[item], examples=[item],
        applications=[item], misconceptions=[item],
    )
    classification = ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                            topic="Motion", chapter="Laws of Motion",
                                            category="STEM", language="English")
    parsed = ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[Section(heading="Intro", text="Body.", page=1)],
    )
    return DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)


PERIOD_SKELETON = {"periods": [
    {"period_no": 1, "duration_min": 40, "title": "Intro to Inertia", "objectives": ["Explain inertia"],
     "concepts_covered": ["Inertia"], "sequencing_notes": "First concept."},
    {"period_no": 2, "duration_min": 40, "title": "Applying Inertia", "objectives": ["Apply inertia"],
     "concepts_covered": ["Inertia"], "sequencing_notes": "Builds on period 1."},
]}

CONTENT_RESPONSE = {
    "entry_ticket": "e", "teacher_script": "s", "blackboard_notes": "b",
    "checkpoint_questions": ["q"], "exit_ticket": "x", "homework": "h", "mentor_moment": "m",
    "grounded_notes": [{"text": "Inertia", "source_ref": {"page": 1, "section": None}}],
}
ACTIVITIES_RESPONSE = {"activities": [
    {"type": "demo", "duration_min": 10, "materials": ["ball"], "teacher_instructions": "roll it", "success_criteria": "predicts motion"}
]}
ASSESSMENT_RESPONSE = {"mcqs": ["q"], "short_answer": ["q"], "long_answer": ["q"], "numerical": ["q"], "answer_key": "k", "rubric": "r"}
GAPS_RESPONSE = {"gap_analysis": [
    {"misconception": {"text": "Inertia", "source_ref": {"page": 1, "section": None}},
     "diagnostic_questions": ["q"], "severity": "low", "remedial_action": "a"}
]}


def test_run_plan_pipeline_completes_with_two_periods(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    job_manager.update_job(source_job_id, status="completed", result_path="/tmp/DocumentKnowledgeExtract.json")
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)

    with patch("app.jobs.pipeline_plan.plan_periods") as mock_plan, \
         patch("app.jobs.pipeline_plan.generate_content") as mock_content, \
         patch("app.jobs.pipeline_plan.generate_activities") as mock_activities, \
         patch("app.jobs.pipeline_plan.generate_assessment") as mock_assessment, \
         patch("app.jobs.pipeline_plan.generate_gaps") as mock_gaps:
        from app.schemas.planning import Activity, Assessment, GapAnalysisItem, PeriodContent, TeachingPlanSkeleton

        mock_plan.return_value = TeachingPlanSkeleton.model_validate(PERIOD_SKELETON)
        mock_content.return_value = PeriodContent.model_validate(CONTENT_RESPONSE)
        mock_activities.return_value = [Activity.model_validate(a) for a in ACTIVITIES_RESPONSE["activities"]]
        mock_assessment.return_value = Assessment.model_validate(ASSESSMENT_RESPONSE)
        mock_gaps.return_value = [GapAnalysisItem.model_validate(g) for g in GAPS_RESPONSE["gap_analysis"]]

        asyncio.run(run_plan_pipeline(job_manager, str(tmp_path), job_id, _source(), source_job_id))

    job = job_manager.get_job(job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert job["result_path"] is not None
    assert mock_content.call_count == 2
    assert mock_activities.call_count == 2
    assert mock_assessment.call_count == 2
    assert mock_gaps.call_count == 1


def test_run_plan_pipeline_marks_failed_on_stage_error(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)

    with patch("app.jobs.pipeline_plan.plan_periods", side_effect=RuntimeError("boom")):
        asyncio.run(run_plan_pipeline(job_manager, str(tmp_path), job_id, _source(), source_job_id))

    job = job_manager.get_job(job_id)
    assert job["status"] == "failed"
    assert "boom" in job["error"]


def test_run_plan_pipeline_fails_when_planner_returns_no_periods(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)

    from app.schemas.planning import TeachingPlanSkeleton

    with patch("app.jobs.pipeline_plan.plan_periods", return_value=TeachingPlanSkeleton(periods=[])):
        asyncio.run(run_plan_pipeline(job_manager, str(tmp_path), job_id, _source(), source_job_id))

    job = job_manager.get_job(job_id)
    assert job["status"] == "failed"
    assert "no periods" in job["error"].lower()
