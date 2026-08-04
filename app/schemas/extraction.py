from typing import Optional

from pydantic import BaseModel


class SourceRef(BaseModel):
    page: Optional[int] = None
    section: Optional[str] = None


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
