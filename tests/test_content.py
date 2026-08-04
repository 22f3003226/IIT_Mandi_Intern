from unittest.mock import MagicMock

import pytest

from app.content.generate import generate_content
from app.llm.openrouter_client import LLMResponseError
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import PeriodPlan


def _period():
    return PeriodPlan(period_no=1, duration_min=40, title="Intro to Inertia",
                        objectives=["Explain inertia"], concepts_covered=["Inertia"],
                        sequencing_notes="First concept.")


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    return KnowledgeExtract(
        learning_objectives=[item], prerequisites=[item], concepts=[item],
        definitions=[item], formulae=[item], keywords=[item], examples=[item],
        applications=[item], misconceptions=[item],
    )


def _classification():
    return ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                  topic="Motion", chapter="Laws of Motion",
                                  category="STEM", language="English")


def _valid_response():
    return {
        "entry_ticket": "What keeps a ball rolling?", "teacher_script": "Today we discuss inertia...",
        "blackboard_notes": "Inertia: resistance to change in motion",
        "checkpoint_questions": ["What is inertia?"], "exit_ticket": "Name one example of inertia",
        "homework": "Find 3 examples of inertia at home", "mentor_moment": "Bus stopping suddenly story",
        "grounded_notes": [{"text": "Inertia", "source_ref": {"page": 1, "section": None}}],
    }


def test_generate_content_returns_valid_period_content():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    result = generate_content(_period(), _knowledge(), _classification(), client=client)
    assert result.entry_ticket == "What keeps a ball rolling?"
    assert result.grounded_notes[0].source_ref.page == 1


def test_generate_content_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    result = generate_content(_period(), _knowledge(), _classification(), client=client)
    assert result.teacher_script.startswith("Today we discuss")
    assert client.complete_json.call_count == 2


def test_generate_content_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        generate_content(_period(), _knowledge(), _classification(), client=client)
    assert client.complete_json.call_count == 3
