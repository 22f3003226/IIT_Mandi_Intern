SYSTEM_PROMPT = """You are an expert in diagnosing student learning gaps. Given the chapter's full
knowledge extract (specifically its "misconceptions" list) and the checkpoint/assessment questions
already generated across all periods of the teaching plan, produce a learning gap analysis: for
each misconception, provide one or more diagnostic questions a teacher could ask to detect whether
a student holds that misconception, a severity level ("low", "medium", or "high") reflecting how
much it would impede understanding of the chapter, and a concrete remedial action the teacher can
take. Ground every misconception in the provided list — do not invent misconceptions absent from
it. You may use general learning-science knowledge to design the diagnostic questions and remedial
actions. Respond ONLY with a JSON object with exactly one key "gap_analysis", an array of objects
each with: misconception (an object with "text" and "source_ref", copied from the input
misconceptions list), diagnostic_questions (array of strings), severity (string: low/medium/high),
remedial_action (string)."""

MAX_CONTEXT_CHARS = 8000


def build_user_prompt(knowledge: dict, periods: list[dict]) -> str:
    checkpoint_questions = [
        q for p in periods
        for q in (p.get("content", {}).get("checkpoint_questions", []) + p.get("assessment", {}).get("mcqs", []))
    ]
    return (
        f"Misconceptions:\n{knowledge.get('misconceptions')}\n\n"
        f"Checkpoint/assessment questions already asked across periods:\n{checkpoint_questions}\n\n"
        f"Full knowledge extract (for context):\n{str(knowledge)[:MAX_CONTEXT_CHARS]}"
    )
