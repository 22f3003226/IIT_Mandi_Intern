from pydantic import BaseModel, field_validator

from app.schemas.extraction import ConceptItem


def _stringify_structured_value(value: object) -> str:
    """Flatten a dict/list a model returned in place of a plain string field."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_stringify_structured_value(v)}" for key, v in value.items())
    if isinstance(value, list):
        return "\n".join(_stringify_structured_value(item) for item in value)
    return str(value)


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
        return _stringify_structured_value(value)


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

    @field_validator("answer_key", "rubric", mode="before")
    @classmethod
    def _flatten_structured_answer_fields(cls, value):
        # models sometimes structure the answer key/rubric per question type
        # instead of writing one plain string
        return _stringify_structured_value(value)


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
