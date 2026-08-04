from pydantic import BaseModel, field_validator

from app.schemas.extraction import ConceptItem


class PeriodPlan(BaseModel):
    period_no: int
    duration_min: int
    title: str
    objectives: list[str]
    concepts_covered: list[str]
    sequencing_notes: str


class TeachingPlanSkeleton(BaseModel):
    periods: list[PeriodPlan]


class PeriodContent(BaseModel):
    entry_ticket: str
    teacher_script: str
    blackboard_notes: str
    checkpoint_questions: list[str]
    exit_ticket: str
    homework: str
    mentor_moment: str
    grounded_notes: list[ConceptItem]

    @field_validator("blackboard_notes", mode="before")
    @classmethod
    def _join_list_notes(cls, value):
        # models often write blackboard notes as bullet points rather than one string
        if isinstance(value, list):
            return "\n".join(str(item) for item in value)
        return value


class Activity(BaseModel):
    type: str
    duration_min: int
    materials: list[str]
    teacher_instructions: str
    success_criteria: str


class ActivitiesResponse(BaseModel):
    activities: list[Activity]


class Assessment(BaseModel):
    mcqs: list[str]
    short_answer: list[str]
    long_answer: list[str]
    numerical: list[str]
    answer_key: str
    rubric: str


class GapAnalysisItem(BaseModel):
    misconception: ConceptItem
    diagnostic_questions: list[str]
    severity: str
    remedial_action: str


class GapAnalysisResponse(BaseModel):
    gap_analysis: list[GapAnalysisItem]


class PeriodPackage(BaseModel):
    plan: PeriodPlan
    content: PeriodContent
    activities: list[Activity]
    assessment: Assessment


class TeachingPlan(BaseModel):
    job_id: str
    source_job_id: str
    periods: list[PeriodPackage]
    gap_analysis: list[GapAnalysisItem]
