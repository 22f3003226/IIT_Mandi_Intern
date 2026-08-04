from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import TeacherKnowledgePackage, ValidationIssue, ValidationReport


def _classification():
    return ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                topic="Motion", chapter="Laws", category="STEM", language="English")


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    return KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                            definitions=[item], formulae=[item], keywords=[item], examples=[item],
                            applications=[item], misconceptions=[item])


def test_validation_report_passed_true_with_no_issues():
    report = ValidationReport(issues=[], passed=True)
    assert report.passed is True
    assert report.issues == []


def test_teacher_knowledge_package_round_trips_through_json():
    report = ValidationReport(
        issues=[ValidationIssue(severity="warning", category="missing_objective",
                                location="period-1", description="No coverage for X")],
        passed=True,
    )
    plan = TeachingPlan(job_id="plan-1", source_job_id="doc-1", periods=[], gap_analysis=[])
    tkp = TeacherKnowledgePackage(
        job_id="publish-1", source_job_id="doc-1", plan_job_id="plan-1",
        classification=_classification(), knowledge=_knowledge(),
        teaching_plan=plan, validation_report=report,
    )
    restored = TeacherKnowledgePackage.model_validate_json(tkp.model_dump_json())
    assert restored.validation_report.issues[0].category == "missing_objective"
    assert restored.plan_job_id == "plan-1"
