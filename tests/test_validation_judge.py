from unittest.mock import MagicMock

import pytest

from app.llm.openrouter_client import LLMResponseError
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import Activity, Assessment, PeriodContent, PeriodPackage, PeriodPlan, TeachingPlan
from app.validation.judge import judge_plan


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    return KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                             definitions=[item], formulae=[item], keywords=[item], examples=[item],
                             applications=[item], misconceptions=[item])


def _plan():
    plan = PeriodPlan(period_no=1, duration_min=40, title="Intro", objectives=["Explain inertia"],
                       concepts_covered=["Inertia"], sequencing_notes="notes")
    content = PeriodContent(entry_ticket="e", teacher_script="s", blackboard_notes="b",
                             checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
                             grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))])
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"], numerical=["q"],
                             answer_key="k", rubric="r")
    package = PeriodPackage(plan=plan, content=content, activities=[], assessment=assessment)
    return TeachingPlan(job_id="j", source_job_id="s", periods=[package], gap_analysis=[])


def _valid_response():
    return {"issues": [
        {"severity": "critical", "category": "hallucination", "location": "period-1",
         "description": "Mentions Newton's Third Law which is not in the source knowledge."},
    ]}


def test_judge_plan_returns_issues():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    issues = judge_plan(_plan(), _knowledge(), client=client)
    assert len(issues) == 1
    assert issues[0].category == "hallucination"


def test_judge_plan_returns_empty_list_when_no_issues():
    client = MagicMock()
    client.complete_json.return_value = {"issues": []}
    issues = judge_plan(_plan(), _knowledge(), client=client)
    assert issues == []


def test_judge_plan_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    issues = judge_plan(_plan(), _knowledge(), client=client)
    assert len(issues) == 1
    assert client.complete_json.call_count == 2


def test_judge_plan_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        judge_plan(_plan(), _knowledge(), client=client)
    assert client.complete_json.call_count == 3
