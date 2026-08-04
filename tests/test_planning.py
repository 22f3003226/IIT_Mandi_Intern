from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.llm.openrouter_client import LLMResponseError
from app.planning.plan import plan_periods
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    return KnowledgeExtract(
        learning_objectives=[item], prerequisites=[item], concepts=[item],
        definitions=[item], formulae=[item], keywords=[item], examples=[item],
        applications=[item], misconceptions=[item],
    )


def _classification():
    return ClassificationResult(
        subject="Physics", grade="9", difficulty="medium", topic="Motion",
        chapter="Laws of Motion", category="STEM", language="English",
    )


def test_plan_periods_returns_valid_skeleton():
    client = MagicMock()
    client.complete_json.return_value = {
        "periods": [
            {"period_no": 1, "duration_min": 40, "title": "Intro to Inertia",
             "objectives": ["Explain inertia"], "concepts_covered": ["Inertia"],
             "sequencing_notes": "First concept taught."}
        ]
    }
    result = plan_periods(_knowledge(), _classification(), client=client)
    assert result.periods[0].title == "Intro to Inertia"
    client.complete_json.assert_called_once()


def test_plan_periods_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [
        LLMResponseError("bad json"),
        {"periods": [{"period_no": 1, "duration_min": 40, "title": "Intro",
                       "objectives": ["obj"], "concepts_covered": ["c"],
                       "sequencing_notes": "notes"}]},
    ]
    result = plan_periods(_knowledge(), _classification(), client=client)
    assert len(result.periods) == 1
    assert client.complete_json.call_count == 2


def test_plan_periods_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        plan_periods(_knowledge(), _classification(), client=client)
    assert client.complete_json.call_count == 3  # MAX_RETRIES=2 + initial attempt
