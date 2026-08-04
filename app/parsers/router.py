from pathlib import Path
from typing import Optional

from app.parsers.docx_parser import parse_docx
from app.parsers.pdf_parser import parse_pdf
from app.parsers.pptx_parser import parse_pptx
from app.parsers.txt_parser import parse_txt
from app.schemas.parsed_document import ParsedDocument

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt"}

EXTENSION_MAP = {
    ".docx": parse_docx,
    ".pptx": parse_pptx,
    ".txt": parse_txt,
}


class UnsupportedFormatError(ValueError):
    pass


def route_and_parse(file_path: str, doc_nature_hint: Optional[str] = None) -> ParsedDocument:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(file_path, doc_nature_hint=doc_nature_hint)
    parser = EXTENSION_MAP.get(ext)
    if parser is None:
        raise UnsupportedFormatError(f"Unsupported file extension: {ext}")
    return parser(file_path)
