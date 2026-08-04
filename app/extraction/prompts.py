SYSTEM_PROMPT = """You are an expert educator building a structured knowledge extraction from a
textbook chapter. Given the document text and its classification, extract: learning_objectives,
prerequisites, concepts, definitions, formulae, keywords, examples, applications, and
misconceptions. Every item MUST include a "source_ref" object with a "page" (int or null) and
"section" (string or null) pointing to where it came from in the source document. Do not invent
facts absent from the source document; you may only draw on outside knowledge to phrase
pedagogy, not to add new subject matter. Respond ONLY with a JSON object with exactly these
keys, each an array of objects with "text" and "source_ref": learning_objectives,
prerequisites, concepts, definitions, formulae, keywords, examples, applications,
misconceptions."""


def build_user_prompt(document_text: str, classification: dict) -> str:
    return f"Classification: {classification}\n\nDocument content:\n\n{document_text[:8000]}"
