from app.schemas.extraction import ConceptItem, SourceRef
from app.schemas.planning import Activity, Assessment, PeriodContent, PeriodPackage, PeriodPlan, TeachingPlan
from app.validation.rules import check_rules


def _package(period_no=1, title="Intro", objectives=None, concepts_covered=None,
             teacher_script="script"):
    plan = PeriodPlan(period_no=period_no, duration_min=40, title=title,
                       objectives=objectives if objectives is not None else ["Explain inertia"],
                       concepts_covered=concepts_covered if concepts_covered is not None else ["Inertia"],
                       sequencing_notes="notes")
    content = PeriodContent(entry_ticket="e", teacher_script=teacher_script, blackboard_notes="b",
                             checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
                             grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))])
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"], numerical=["q"],
                             answer_key="k", rubric="r")
    return PeriodPackage(plan=plan, content=content, activities=[], assessment=assessment)


def test_clean_plan_produces_no_issues():
    plan = TeachingPlan(job_id="j", source_job_id="s", periods=[_package()], gap_analysis=[])
    assert check_rules(plan) == []


def test_period_with_no_objectives_flagged():
    plan = TeachingPlan(job_id="j", source_job_id="s", periods=[_package(objectives=[])], gap_analysis=[])
    issues = check_rules(plan)
    assert any(i.category == "missing_objective" and i.location == "period-1" for i in issues)


def test_duplicate_period_titles_flagged():
    plan = TeachingPlan(
        job_id="j", source_job_id="s",
        periods=[_package(period_no=1, title="Intro"), _package(period_no=2, title="Intro")],
        gap_analysis=[],
    )
    issues = check_rules(plan)
    assert any(i.category == "inconsistency" and "duplicate" in i.description.lower() for i in issues)


def test_blank_teacher_script_flagged():
    plan = TeachingPlan(job_id="j", source_job_id="s", periods=[_package(teacher_script="  ")], gap_analysis=[])
    issues = check_rules(plan)
    assert any(i.category == "schema" and i.location == "period-1" for i in issues)
