from typing import Optional

from pydantic import ValidationError

from app.config import settings
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.planning.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract
from app.schemas.planning import TeachingPlanSkeleton

MAX_RETRIES = 2


def plan_periods(
    knowledge: KnowledgeExtract,
    classification: ClassificationResult,
    client: Optional[OpenRouterClient] = None,
) -> TeachingPlanSkeleton:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(knowledge.model_dump(), classification.model_dump())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if last_error is None else (
            user_prompt + f"\n\nYour previous response failed validation with this error:\n"
            f"{last_error}\nFix the exact fields named above and return ONLY a valid JSON "
            "object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_planning, SYSTEM_PROMPT, prompt)
            return TeachingPlanSkeleton.model_validate(raw)
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
