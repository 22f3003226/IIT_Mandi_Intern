SYSTEM_PROMPT = """You are an expert curriculum classifier. Given the text of an educational
document, determine its Subject, Grade level, Difficulty, Topic, Chapter name, Category
(e.g. STEM, Humanities, Language), and Language. Base your answer only on the document
content provided; do not assume a specific curriculum board unless stated. Respond ONLY
with a JSON object with exactly these keys: subject, grade, difficulty, topic, chapter,
category, language."""


def build_user_prompt(document_text: str) -> str:
    return f"Document content:\n\n{document_text[:8000]}"
