from unittest.mock import MagicMock

import pytest

from app.gaps.generate import generate_gaps
from app.llm.openrouter_client import LLMResponseError
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import Assessment, PeriodContent, PeriodPackage, PeriodPlan


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    misconception = ConceptItem(text="Objects need a constant push to keep moving", source_ref=SourceRef(page=2))
    return KnowledgeExtract(
        learning_objectives=[item], prerequisites=[item], concepts=[item],
        definitions=[item], formulae=[item], keywords=[item], examples=[item],
        applications=[item], misconceptions=[misconception],
    )


def _period_package():
    plan = PeriodPlan(period_no=1, duration_min=40, title="Intro", objectives=["obj"],
                        concepts_covered=["c"], sequencing_notes="notes")
    content = PeriodContent(entry_ticket="e", teacher_script="s", blackboard_notes="b",
                              checkpoint_questions=["What is inertia?"], exit_ticket="x",
                              homework="h", mentor_moment="m",
                              grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))])
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"], numerical=["q"],
                              answer_key="k", rubric="r")
    return PeriodPackage(plan=plan, content=content, activities=[], assessment=assessment)


def _valid_response():
    return {"gap_analysis": [
        {"misconception": {"text": "Objects need a constant push to keep moving",
                             "source_ref": {"page": 2, "section": None}},
         "diagnostic_questions": ["Does a hockey puck slow down due to lack of force or due to friction?"],
         "severity": "high", "remedial_action": "Demonstrate motion on a low-friction surface"}
    ]}


def test_generate_gaps_returns_list():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    result = generate_gaps(_knowledge(), [_period_package()], client=client)
    assert len(result) == 1
    assert result[0].severity == "high"


def test_generate_gaps_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    result = generate_gaps(_knowledge(), [_period_package()], client=client)
    assert len(result) == 1
    assert client.complete_json.call_count == 2


def test_generate_gaps_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        generate_gaps(_knowledge(), [_period_package()], client=client)
    assert client.complete_json.call_count == 3
