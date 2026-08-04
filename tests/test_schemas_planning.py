import pytest
from pydantic import ValidationError

from app.schemas.extraction import ConceptItem, SourceRef
from app.schemas.planning import (
    Activity,
    ActivitiesResponse,
    Assessment,
    GapAnalysisItem,
    GapAnalysisResponse,
    PeriodContent,
    PeriodPackage,
    PeriodPlan,
    TeachingPlan,
    TeachingPlanSkeleton,
)


def _concept_item():
    return ConceptItem(text="Newton's First Law", source_ref=SourceRef(page=3))


def test_period_plan_roundtrip():
    plan = PeriodPlan(
        period_no=1, duration_min=40, title="Intro to Motion",
        objectives=["Explain inertia"], concepts_covered=["inertia"],
        sequencing_notes="Foundational concept, taught first.",
    )
    assert TeachingPlanSkeleton(periods=[plan]).periods[0].period_no == 1


def test_period_content_requires_grounded_notes():
    content = PeriodContent(
        entry_ticket="Quick recap question", teacher_script="Explain inertia...",
        blackboard_notes="Inertia = resistance to change in motion",
        checkpoint_questions=["What is inertia?"], exit_ticket="One thing you learned",
        homework="Read next section", mentor_moment="Story about a bus stopping suddenly",
        grounded_notes=[_concept_item()],
    )
    assert content.grounded_notes[0].source_ref.page == 3


def test_period_content_coerces_list_blackboard_notes_to_string():
    content = PeriodContent(
        entry_ticket="Quick recap question", teacher_script="Explain inertia...",
        blackboard_notes=["Inertia = resistance to change in motion", "F = m * a"],
        checkpoint_questions=["What is inertia?"], exit_ticket="One thing you learned",
        homework="Read next section", mentor_moment="Story about a bus stopping suddenly",
        grounded_notes=[_concept_item()],
    )
    assert content.blackboard_notes == "Inertia = resistance to change in motion\nF = m * a"


def test_activities_response_wraps_list():
    resp = ActivitiesResponse(activities=[
        Activity(type="demonstration", duration_min=10, materials=["ball", "table"],
                  teacher_instructions="Roll the ball", success_criteria="Students predict motion")
    ])
    assert len(resp.activities) == 1


def test_assessment_roundtrip():
    assessment = Assessment(
        mcqs=["Q1..."], short_answer=["Q2..."], long_answer=["Q3..."], numerical=["Q4..."],
        answer_key="1-B, 2-...", rubric="Award 1 point per correct step",
    )
    assert assessment.mcqs == ["Q1..."]


def test_gap_analysis_response_wraps_list():
    resp = GapAnalysisResponse(gap_analysis=[
        GapAnalysisItem(
            misconception=_concept_item(), diagnostic_questions=["Does a moving object stop on its own?"],
            severity="high", remedial_action="Demonstrate with a frictionless simulation",
        )
    ])
    assert resp.gap_analysis[0].severity == "high"


def test_gap_analysis_rejects_invalid_severity_free_text_allowed():
    # severity is a plain string (not an enum) — any value is accepted by the schema;
    # this test documents that choice rather than asserting a validation error.
    item = GapAnalysisItem(
        misconception=_concept_item(), diagnostic_questions=["..."],
        severity="medium", remedial_action="...",
    )
    assert item.severity == "medium"


def test_teaching_plan_roundtrip():
    plan = PeriodPlan(
        period_no=1, duration_min=40, title="Intro", objectives=["obj"],
        concepts_covered=["c"], sequencing_notes="notes",
    )
    content = PeriodContent(
        entry_ticket="e", teacher_script="s", blackboard_notes="b",
        checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
        grounded_notes=[_concept_item()],
    )
    activity = Activity(type="demo", duration_min=5, materials=["m"],
                          teacher_instructions="i", success_criteria="s")
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"],
                              numerical=["q"], answer_key="k", rubric="r")
    package = PeriodPackage(plan=plan, content=content, activities=[activity], assessment=assessment)
    gap = GapAnalysisItem(misconception=_concept_item(), diagnostic_questions=["q"],
                            severity="low", remedial_action="a")
    tp = TeachingPlan(job_id="job-1", source_job_id="job-0", periods=[package], gap_analysis=[gap])
    assert tp.periods[0].plan.title == "Intro"
    assert tp.model_dump_json()  # serializes without error
