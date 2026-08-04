from pydantic import BaseModel

from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract
from app.schemas.parsed_document import ParsedDocument


class DocumentKnowledgeExtract(BaseModel):
    parsed_document: ParsedDocument
    classification: ClassificationResult
    knowledge: KnowledgeExtract
