from typing import Optional

from pydantic import ValidationError

from app.config import settings
from app.content.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract
from app.schemas.planning import PeriodContent, PeriodPlan

MAX_RETRIES = 2


def generate_content(
    period: PeriodPlan,
    knowledge: KnowledgeExtract,
    classification: ClassificationResult,
    client: Optional[OpenRouterClient] = None,
) -> PeriodContent:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(period.model_dump(), knowledge.model_dump(), classification.model_dump())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid JSON or missing required "
            "keys. Return ONLY a valid JSON object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_content, SYSTEM_PROMPT, prompt)
            return PeriodContent.model_validate(raw)
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
