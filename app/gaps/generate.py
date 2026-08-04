from typing import Optional

from pydantic import ValidationError

from app.config import settings
from app.gaps.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.extraction import KnowledgeExtract
from app.schemas.planning import GapAnalysisItem, GapAnalysisResponse, PeriodPackage

MAX_RETRIES = 2


def generate_gaps(
    knowledge: KnowledgeExtract,
    periods: list[PeriodPackage],
    client: Optional[OpenRouterClient] = None,
) -> list[GapAnalysisItem]:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(knowledge.model_dump(), [p.model_dump() for p in periods])

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if last_error is None else (
            user_prompt + f"\n\nYour previous response failed validation with this error:\n"
            f"{last_error}\nFix the exact fields named above and return ONLY a valid JSON "
            "object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_gaps, SYSTEM_PROMPT, prompt)
            return GapAnalysisResponse.model_validate(raw).gap_analysis
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
