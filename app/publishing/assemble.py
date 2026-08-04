from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import TeacherKnowledgePackage, ValidationReport


def assemble_tkp(
    job_id: str,
    source_job_id: str,
    plan_job_id: str,
    source: DocumentKnowledgeExtract,
    plan: TeachingPlan,
    validation_report: ValidationReport,
) -> TeacherKnowledgePackage:
    return TeacherKnowledgePackage(
        job_id=job_id,
        source_job_id=source_job_id,
        plan_job_id=plan_job_id,
        classification=source.classification,
        knowledge=source.knowledge,
        teaching_plan=plan,
        validation_report=validation_report,
    )
