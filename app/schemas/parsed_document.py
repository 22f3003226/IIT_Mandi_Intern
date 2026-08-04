from typing import Optional

from pydantic import BaseModel


class Section(BaseModel):
    heading: Optional[str] = None
    level: int = 0
    text: str
    page: Optional[int] = None


class TableBlock(BaseModel):
    page: Optional[int] = None
    rows: list[list[str]]


class FigureRef(BaseModel):
    page: Optional[int] = None
    caption: Optional[str] = None


class EquationRef(BaseModel):
    page: Optional[int] = None
    text: str


class DocumentMetadata(BaseModel):
    source_filename: str
    format: str
    page_count: int
    detected_language: Optional[str] = None


class ParsedDocument(BaseModel):
    metadata: DocumentMetadata
    sections: list[Section] = []
    tables: list[TableBlock] = []
    figures: list[FigureRef] = []
    equations: list[EquationRef] = []

    def flatten_text(self) -> str:
        return "\n\n".join(f"[page {s.page}] {s.heading or ''}\n{s.text}" for s in self.sections)
