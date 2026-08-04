from app.extraction.extract import extract
from app.schemas.classification import ClassificationResult
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section


def make_parsed():
    return ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[Section(heading="Newtons First Law", text="An object at rest stays at rest.")],
    )


def make_classification():
    return ClassificationResult(
        subject="Physics", grade="9", difficulty="medium", topic="Motion",
        chapter="Laws of Motion", category="STEM", language="English",
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete_json(self, model, system_prompt, user_prompt):
        response = self.responses[self.calls]
        self.calls += 1
        return response


VALID_EXTRACTION = {
    "learning_objectives": [{"text": "Understand inertia", "source_ref": {"page": 1, "section": "Newtons First Law"}}],
    "prerequisites": [],
    "concepts": [{"text": "Inertia", "source_ref": {"page": 1, "section": "Newtons First Law"}}],
    "definitions": [],
    "formulae": [],
    "keywords": [{"text": "inertia", "source_ref": {"page": 1, "section": None}}],
    "examples": [],
    "applications": [],
    "misconceptions": [],
}


def test_extract_returns_valid_result_on_first_try():
    client = FakeClient([VALID_EXTRACTION])
    result = extract(make_parsed(), make_classification(), client=client)
    assert result.concepts[0].text == "Inertia"
    assert client.calls == 1


def test_extract_retries_on_invalid_schema_then_succeeds():
    client = FakeClient([{"learning_objectives": []}, VALID_EXTRACTION])
    result = extract(make_parsed(), make_classification(), client=client)
    assert result.keywords[0].text == "inertia"
    assert client.calls == 2
