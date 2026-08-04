import pytest
from pydantic import ValidationError

from app.schemas.classification import ClassificationResult
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section


def test_parsed_document_flatten_text_joins_sections():
    doc = ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[
            Section(heading="Intro", text="Body one."),
            Section(heading=None, text="Body two."),
        ],
    )
    flat = doc.flatten_text()
    assert "Intro" in flat
    assert "Body one." in flat
    assert "Body two." in flat


def test_document_knowledge_extract_round_trips_json():
    doc = ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
    )
    classification = ClassificationResult(
        subject="Physics", grade="9", difficulty="medium", topic="Motion",
        chapter="Laws of Motion", category="STEM", language="English",
    )
    knowledge = KnowledgeExtract(
        learning_objectives=[ConceptItem(text="Understand inertia", source_ref=SourceRef(page=1))],
        prerequisites=[], concepts=[], definitions=[], formulae=[],
        keywords=[], examples=[], applications=[], misconceptions=[],
    )
    package = DocumentKnowledgeExtract(parsed_document=doc, classification=classification, knowledge=knowledge)

    raw = package.model_dump_json()
    restored = DocumentKnowledgeExtract.model_validate_json(raw)
    assert restored.classification.subject == "Physics"
    assert restored.knowledge.learning_objectives[0].text == "Understand inertia"


def test_source_ref_rejects_fully_empty_pointer():
    with pytest.raises(ValidationError):
        SourceRef(page=None, section=None)


def test_concept_item_coerces_bare_section_string_into_source_ref():
    item = ConceptItem(text="Newton's First Law", source_ref="Newton's First Law of Motion")
    assert item.source_ref.section == "Newton's First Law of Motion"
    assert item.source_ref.page is None


def test_flatten_text_includes_page_marker():
    doc = ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[Section(heading="Intro", text="Body.", page=3)],
    )
    assert "[page 3]" in doc.flatten_text()
