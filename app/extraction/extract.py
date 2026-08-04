from typing import Optional

from pydantic import ValidationError

from app.config import settings
from app.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract
from app.schemas.parsed_document import ParsedDocument

MAX_RETRIES = 2


def extract(
    parsed: ParsedDocument,
    classification: ClassificationResult,
    client: Optional[OpenRouterClient] = None,
) -> KnowledgeExtract:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(parsed, classification.model_dump())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if last_error is None else (
            user_prompt + f"\n\nYour previous response failed validation with this error:\n"
            f"{last_error}\nFix the exact fields named above and return ONLY a valid JSON "
            "object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_extraction, SYSTEM_PROMPT, prompt)
            return KnowledgeExtract.model_validate(raw)
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
