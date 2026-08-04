from typing import Optional

from app.llm.openrouter_client import OpenRouterClient
from app.schemas.extraction import KnowledgeExtract
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import ValidationReport
from app.validation.judge import judge_plan
from app.validation.rules import check_rules


def validate(
    plan: TeachingPlan,
    knowledge: KnowledgeExtract,
    client: Optional[OpenRouterClient] = None,
) -> ValidationReport:
    issues = check_rules(plan) + judge_plan(plan, knowledge, client=client)
    passed = not any(issue.severity == "critical" for issue in issues)
    return ValidationReport(issues=issues, passed=passed)
