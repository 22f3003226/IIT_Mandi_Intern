from pathlib import Path
from typing import Optional

import fitz
import pdfplumber

from app.parsers.base import looks_like_equation, looks_like_heading
from app.parsers.ocr import ocr_page_text
from app.schemas.parsed_document import (
    DocumentMetadata,
    EquationRef,
    FigureRef,
    ParsedDocument,
    Section,
    TableBlock,
)

OCR_TRIGGER_CHAR_COUNT = 20


def parse_pdf(file_path: str, doc_nature_hint: Optional[str] = None) -> ParsedDocument:
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        page_texts = [(page.extract_text() or "") for page in pdf.pages]
        tables: list[TableBlock] = []
        for page_index, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                tables.append(TableBlock(page=page_index, rows=[[cell or "" for cell in row] for row in table]))

    total_chars = sum(len(t.strip()) for t in page_texts)
    if doc_nature_hint == "Scanned PDF" or total_chars < OCR_TRIGGER_CHAR_COUNT:
        with fitz.open(file_path) as doc:
            page_texts = [ocr_page_text(doc, i) for i in range(page_count)]

    sections: list[Section] = []
    equations: list[EquationRef] = []
    for page_index, text in enumerate(page_texts, start=1):
        current_heading: Optional[str] = None
        buffer: list[str] = []
        for line in text.splitlines():
            if looks_like_equation(line):
                equations.append(EquationRef(page=page_index, text=line.strip()))
            if looks_like_heading(line):
                if buffer:
                    sections.append(Section(heading=current_heading, page=page_index, text="\n".join(buffer).strip()))
                buffer = []
                current_heading = line.strip()
            else:
                buffer.append(line)
        if buffer:
            sections.append(Section(heading=current_heading, page=page_index, text="\n".join(buffer).strip()))

    figures: list[FigureRef] = []
    with fitz.open(file_path) as doc:
        for page_index in range(len(doc)):
            image_count = len(doc[page_index].get_images())
            figures.extend(FigureRef(page=page_index + 1) for _ in range(image_count))

    return ParsedDocument(
        metadata=DocumentMetadata(source_filename=Path(file_path).name, format="pdf", page_count=page_count),
        sections=[s for s in sections if s.text],
        tables=tables,
        figures=figures,
        equations=equations,
    )
