from typing import Optional

from pydantic import ValidationError

from app.classification.prompts import SYSTEM_PROMPT, build_user_prompt
from app.config import settings
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.classification import ClassificationResult
from app.schemas.parsed_document import ParsedDocument

MAX_RETRIES = 2


def classify(parsed: ParsedDocument, client: Optional[OpenRouterClient] = None) -> ClassificationResult:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(parsed.flatten_text())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid. Return ONLY a valid JSON "
            "object with keys: subject, grade, difficulty, topic, chapter, category, language."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_classification, SYSTEM_PROMPT, prompt)
            return ClassificationResult.model_validate(raw)
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
