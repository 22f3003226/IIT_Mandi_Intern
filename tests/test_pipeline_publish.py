import asyncio
from pathlib import Path
from unittest.mock import patch

from app.jobs.manager import JobManager
from app.jobs.pipeline_publish import run_publish_pipeline
from app.schemas.classification import ClassificationResult
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section
from app.schemas.planning import Activity, Assessment, PeriodContent, PeriodPackage, PeriodPlan, TeachingPlan
from app.schemas.publishing import ValidationReport


def _source():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    knowledge = KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                                  definitions=[item], formulae=[item], keywords=[item], examples=[item],
                                  applications=[item], misconceptions=[item])
    classification = ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                           topic="Motion", chapter="Laws", category="STEM", language="English")
    parsed = ParsedDocument(metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
                             sections=[Section(heading="Intro", text="Body.", page=1)])
    return DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)


def _plan():
    plan_item = PeriodPlan(period_no=1, duration_min=40, title="Intro", objectives=["Explain inertia"],
                            concepts_covered=["Inertia"], sequencing_notes="notes")
    content = PeriodContent(entry_ticket="e", teacher_script="s", blackboard_notes="b",
                             checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
                             grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))])
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"], numerical=["q"],
                             answer_key="k", rubric="r")
    package = PeriodPackage(plan=plan_item, content=content, activities=[], assessment=assessment)
    return TeachingPlan(job_id="plan-1", source_job_id="doc-1", periods=[package], gap_analysis=[])


def test_run_publish_pipeline_completes_and_writes_all_outputs(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish", parent_job_id=plan_job_id)

    with patch("app.jobs.pipeline_publish.validate") as mock_validate:
        mock_validate.return_value = ValidationReport(issues=[], passed=True)
        asyncio.run(run_publish_pipeline(job_manager, str(tmp_path), job_id, _source(), _plan(),
                                          plan_job_id, source_job_id))

    job = job_manager.get_job(job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert Path(job["result_path"]).name == "TeacherKnowledgePackage.json"
    assert (tmp_path / job_id / "lesson-plan.pdf").exists()
    assert (tmp_path / job_id / "teacher-guide.pdf").exists()
    assert (tmp_path / job_id / "assessment-book.pdf").exists()


def test_run_publish_pipeline_marks_failed_on_stage_error(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish", parent_job_id=plan_job_id)

    with patch("app.jobs.pipeline_publish.validate", side_effect=RuntimeError("boom")):
        asyncio.run(run_publish_pipeline(job_manager, str(tmp_path), job_id, _source(), _plan(),
                                          plan_job_id, source_job_id))

    job = job_manager.get_job(job_id)
    assert job["status"] == "failed"
    assert "boom" in job["error"]
