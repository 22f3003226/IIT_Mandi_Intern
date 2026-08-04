from typing import Optional

from pydantic import ValidationError

from app.activities.prompts import SYSTEM_PROMPT, build_user_prompt
from app.config import settings
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.classification import ClassificationResult
from app.schemas.planning import Activity, ActivitiesResponse, PeriodContent, PeriodPlan

MAX_RETRIES = 2


def generate_activities(
    period: PeriodPlan,
    classification: ClassificationResult,
    content: PeriodContent,
    client: Optional[OpenRouterClient] = None,
) -> list[Activity]:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(period.model_dump(), classification.model_dump(), content.model_dump())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid JSON or missing required "
            "keys. Return ONLY a valid JSON object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_activities, SYSTEM_PROMPT, prompt)
            return ActivitiesResponse.model_validate(raw).activities
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
