from pydantic import BaseModel

from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract
from app.schemas.planning import TeachingPlan


class ValidationIssue(BaseModel):
    severity: str  # "critical" | "warning" | "info"
    category: str  # "hallucination" | "missing_objective" | "inconsistency" | "schema"
    location: str  # e.g. "period-3" or "plan"
    description: str


class ValidationReport(BaseModel):
    issues: list[ValidationIssue]
    passed: bool


class TeacherKnowledgePackage(BaseModel):
    job_id: str
    source_job_id: str
    plan_job_id: str
    classification: ClassificationResult
    knowledge: KnowledgeExtract
    teaching_plan: TeachingPlan
    validation_report: ValidationReport
