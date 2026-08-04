from app.schemas.planning import TeachingPlan
from app.schemas.publishing import ValidationIssue


def check_rules(plan: TeachingPlan) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_titles: dict[str, int] = {}

    for package in plan.periods:
        period = package.plan
        location = f"period-{period.period_no}"

        if not period.objectives:
            issues.append(ValidationIssue(
                severity="critical", category="missing_objective", location=location,
                description="Period has no learning objectives.",
            ))

        if not package.content.teacher_script.strip():
            issues.append(ValidationIssue(
                severity="critical", category="schema", location=location,
                description="Teacher script is blank.",
            ))

        seen_titles[period.title] = seen_titles.get(period.title, 0) + 1

    for title, count in seen_titles.items():
        if count > 1:
            issues.append(ValidationIssue(
                severity="warning", category="inconsistency", location="plan",
                description=f"Duplicate period title used {count} times: {title!r}",
            ))

    return issues
