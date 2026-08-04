from pydantic import BaseModel


class ClassificationResult(BaseModel):
    subject: str
    grade: str
    difficulty: str
    topic: str
    chapter: str
    category: str
    language: str
