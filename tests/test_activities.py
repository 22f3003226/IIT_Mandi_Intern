from unittest.mock import MagicMock

import pytest

from app.activities.generate import generate_activities
from app.llm.openrouter_client import LLMResponseError
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, SourceRef
from app.schemas.planning import PeriodContent, PeriodPlan


def _period():
    return PeriodPlan(period_no=1, duration_min=40, title="Intro to Inertia",
                        objectives=["Explain inertia"], concepts_covered=["Inertia"],
                        sequencing_notes="First concept.")


def _classification():
    return ClassificationResult(subject="Physics", grade="9", difficulty="medium", topic="Motion",
                                 chapter="Laws of Motion", category="STEM", language="English")


def _content():
    return PeriodContent(
        entry_ticket="e", teacher_script="s", blackboard_notes="b",
        checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
        grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))],
    )


def _valid_response():
    return {"activities": [
        {"type": "demonstration", "duration_min": 10, "materials": ["ball", "table"],
         "teacher_instructions": "Roll the ball across the table", "success_criteria": "Students predict it keeps moving"},
    ]}


def test_generate_activities_returns_list():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    result = generate_activities(_period(), _classification(), _content(), client=client)
    assert len(result) == 1
    assert result[0].type == "demonstration"


def test_generate_activities_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    result = generate_activities(_period(), _classification(), _content(), client=client)
    assert len(result) == 1
    assert client.complete_json.call_count == 2


def test_generate_activities_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        generate_activities(_period(), _classification(), _content(), client=client)
    assert client.complete_json.call_count == 3
