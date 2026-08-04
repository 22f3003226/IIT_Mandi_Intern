from app.publishing.pdf import render_assessment_book_pdf, render_lesson_plan_pdf, render_teacher_guide_pdf
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import Activity, Assessment, PeriodContent, PeriodPackage, PeriodPlan, TeachingPlan
from app.schemas.publishing import TeacherKnowledgePackage, ValidationReport


def _tkp():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    knowledge = KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                                  definitions=[item], formulae=[item], keywords=[item], examples=[item],
                                  applications=[item], misconceptions=[item])
    classification = ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                           topic="Motion", chapter="Laws of Motion", category="STEM",
                                           language="English")
    plan_item = PeriodPlan(period_no=1, duration_min=40, title="Intro", objectives=["Explain inertia"],
                            concepts_covered=["Inertia"], sequencing_notes="First period.")
    content = PeriodContent(entry_ticket="e", teacher_script="Explain that objects resist changes in motion.",
                             blackboard_notes="F = m*a", checkpoint_questions=["What is inertia?"],
                             exit_ticket="x", homework="h", mentor_moment="Newton once said...",
                             grounded_notes=[item])
    activities = [Activity(type="demo", duration_min=10, materials=["ball"],
                            teacher_instructions="Roll the ball", success_criteria="Predicts motion")]
    assessment = Assessment(mcqs=["What is inertia?"], short_answer=["Define inertia"],
                             long_answer=["Explain inertia with an example"], numerical=["Calc F=ma"],
                             answer_key="See above", rubric="1 point each")
    package = PeriodPackage(plan=plan_item, content=content, activities=activities, assessment=assessment)
    plan = TeachingPlan(job_id="plan-1", source_job_id="doc-1", periods=[package], gap_analysis=[])
    report = ValidationReport(issues=[], passed=True)
    return TeacherKnowledgePackage(job_id="pub-1", source_job_id="doc-1", plan_job_id="plan-1",
                                    classification=classification, knowledge=knowledge,
                                    teaching_plan=plan, validation_report=report)


def test_render_lesson_plan_pdf_produces_nonempty_bytes():
    pdf_bytes = render_lesson_plan_pdf(_tkp())
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 100


def test_render_teacher_guide_pdf_produces_nonempty_bytes():
    pdf_bytes = render_teacher_guide_pdf(_tkp())
    assert pdf_bytes.startswith(b"%PDF")


def test_render_assessment_book_pdf_produces_nonempty_bytes():
    pdf_bytes = render_assessment_book_pdf(_tkp())
    assert pdf_bytes.startswith(b"%PDF")
