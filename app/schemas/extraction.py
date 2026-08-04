from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class SourceRef(BaseModel):
    page: Optional[int] = None
    section: Optional[str] = None

    @model_validator(mode="after")
    def _require_a_pointer(self):
        if self.page is None and self.section is None:
            raise ValueError("source_ref must specify at least one of page or section")
        return self


class ConceptItem(BaseModel):
    text: str
    source_ref: SourceRef

    @field_validator("source_ref", mode="before")
    @classmethod
    def _coerce_bare_section_string(cls, value):
        # models sometimes write the section heading directly instead of
        # {"page": ..., "section": ...}
        if isinstance(value, str):
            return {"section": value}
        return value


class KnowledgeExtract(BaseModel):
    learning_objectives: list[ConceptItem]
    prerequisites: list[ConceptItem]
    concepts: list[ConceptItem]
    definitions: list[ConceptItem]
    formulae: list[ConceptItem]
    keywords: list[ConceptItem]
    examples: list[ConceptItem]
    applications: list[ConceptItem]
    misconceptions: list[ConceptItem]
