SYSTEM_PROMPT = """You are an expert curriculum planner. Given a chapter's structured knowledge
extract (learning objectives, prerequisites, concepts, definitions, formulae, examples) and its
classification (grade/subject/difficulty), design a multi-period teaching plan. Decide the number
of periods and each period's duration based on content volume, conceptual complexity, and the
target grade level — do not assume a fixed number of periods or a fixed duration such as "5
periods of 40 minutes" unless the content genuinely calls for it. Every period must have a title,
one or more objectives, the concepts it covers (drawn only from the provided concepts/definitions,
not invented), and sequencing_notes explaining why it comes at that point in the chapter. You may
use general pedagogy knowledge to decide sequencing and pacing, but every concept named must come
from the provided knowledge extract — do not introduce subject matter absent from it. Respond ONLY
with a JSON object with exactly one key "periods", an array of objects each with: period_no (int),
duration_min (int), title (string), objectives (array of strings), concepts_covered (array of
strings), sequencing_notes (string)."""

MAX_CONTEXT_CHARS = 8000


def build_user_prompt(knowledge: dict, classification: dict) -> str:
    return (
        f"Classification: {classification}\n\n"
        f"Knowledge extract:\n{str(knowledge)[:MAX_CONTEXT_CHARS]}"
    )
