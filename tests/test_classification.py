from app.classification.classify import classify
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section


def make_parsed():
    return ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[Section(heading="Newtons First Law", text="An object at rest stays at rest.")],
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete_json(self, model, system_prompt, user_prompt):
        response = self.responses[self.calls]
        self.calls += 1
        return response


def test_classify_returns_valid_result_on_first_try():
    client = FakeClient([{
        "subject": "Physics", "grade": "9", "difficulty": "medium", "topic": "Motion",
        "chapter": "Laws of Motion", "category": "STEM", "language": "English",
    }])
    result = classify(make_parsed(), client=client)
    assert result.subject == "Physics"
    assert client.calls == 1


def test_classify_retries_on_invalid_schema_then_succeeds():
    client = FakeClient([
        {"subject": "Physics"},
        {
            "subject": "Physics", "grade": "9", "difficulty": "medium", "topic": "Motion",
            "chapter": "Laws of Motion", "category": "STEM", "language": "English",
        },
    ])
    result = classify(make_parsed(), client=client)
    assert result.grade == "9"
    assert client.calls == 2
