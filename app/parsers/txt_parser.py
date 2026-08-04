from pathlib import Path
from typing import Optional

from app.parsers.base import looks_like_equation, looks_like_heading
from app.schemas.parsed_document import DocumentMetadata, EquationRef, ParsedDocument, Section


def parse_txt(file_path: str) -> ParsedDocument:
    text = Path(file_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    sections: list[Section] = []
    equations: list[EquationRef] = []
    current_heading: Optional[str] = None
    buffer: list[str] = []

    for line in lines:
        if looks_like_equation(line):
            equations.append(EquationRef(text=line.strip()))
        if looks_like_heading(line):
            if buffer:
                sections.append(Section(heading=current_heading, text="\n".join(buffer).strip()))
            buffer = []
            current_heading = line.strip()
        else:
            buffer.append(line)
    if buffer:
        sections.append(Section(heading=current_heading, text="\n".join(buffer).strip()))

    return ParsedDocument(
        metadata=DocumentMetadata(source_filename=Path(file_path).name, format="txt", page_count=1),
        sections=[s for s in sections if s.text],
        equations=equations,
    )
