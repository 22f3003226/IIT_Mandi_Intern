SYSTEM_PROMPT = """You are an expert educator building a structured knowledge extraction from a
textbook chapter. Given the document text and its classification, extract: learning_objectives,
prerequisites, concepts, definitions, formulae, keywords, examples, applications, and
misconceptions. Every item MUST include a "source_ref" object with a "page" (int or null) and
"section" (string or null) pointing to where it came from in the source document; at least one
of page/section must be set. Do not invent facts absent from the source document; you may only
draw on outside knowledge to phrase pedagogy, not to add new subject matter. Tables and
equations detected in the document are listed separately below the main text — use them as
source material too, especially for "formulae". Respond ONLY with a JSON object with exactly
these keys, each an array of objects with "text" and "source_ref": learning_objectives,
prerequisites, concepts, definitions, formulae, keywords, examples, applications,
misconceptions."""

MAX_DOCUMENT_CHARS = 8000


def build_user_prompt(parsed, classification: dict) -> str:
    equations_block = "\n".join(f"- [page {e.page}] {e.text}" for e in parsed.equations) or "(none detected)"
    tables_block = "\n".join(f"- [page {t.page}] {t.rows}" for t in parsed.tables) or "(none detected)"
    return (
        f"Classification: {classification}\n\n"
        f"Document content:\n\n{parsed.flatten_text()[:MAX_DOCUMENT_CHARS]}\n\n"
        f"Equations detected:\n{equations_block}\n\n"
        f"Tables detected:\n{tables_block}"
    )
