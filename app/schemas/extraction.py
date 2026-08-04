from typing import Optional

from pydantic import BaseModel, model_validator


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
