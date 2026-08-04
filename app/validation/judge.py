from typing import Optional

from pydantic import BaseModel, ValidationError

from app.config import settings
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.extraction import KnowledgeExtract
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import ValidationIssue
from app.validation.prompts import SYSTEM_PROMPT, build_user_prompt

MAX_RETRIES = 2


class _JudgeResponse(BaseModel):
    issues: list[ValidationIssue]


def judge_plan(
    plan: TeachingPlan,
    knowledge: KnowledgeExtract,
    client: Optional[OpenRouterClient] = None,
) -> list[ValidationIssue]:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(plan.model_dump(), knowledge.model_dump())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid JSON or missing required "
            "keys. Return ONLY a valid JSON object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_validation, SYSTEM_PROMPT, prompt)
            return _JudgeResponse.model_validate(raw).issues
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
