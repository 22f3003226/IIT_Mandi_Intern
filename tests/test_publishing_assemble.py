from app.publishing.assemble import assemble_tkp
from app.schemas.classification import ClassificationResult
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import ValidationReport


def test_assemble_tkp_combines_all_inputs():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    knowledge = KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                                  definitions=[item], formulae=[item], keywords=[item], examples=[item],
                                  applications=[item], misconceptions=[item])
    classification = ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                           topic="Motion", chapter="Laws", category="STEM", language="English")
    parsed = ParsedDocument(metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
                             sections=[Section(heading="Intro", text="Body.", page=1)])
    source = DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)
    plan = TeachingPlan(job_id="plan-1", source_job_id="doc-1", periods=[], gap_analysis=[])
    report = ValidationReport(issues=[], passed=True)

    tkp = assemble_tkp(job_id="pub-1", source_job_id="doc-1", plan_job_id="plan-1",
                        source=source, plan=plan, validation_report=report)

    assert tkp.job_id == "pub-1"
    assert tkp.classification.subject == "Physics"
    assert tkp.knowledge.concepts[0].text == "Inertia"
    assert tkp.teaching_plan.job_id == "plan-1"
    assert tkp.validation_report.passed is True
