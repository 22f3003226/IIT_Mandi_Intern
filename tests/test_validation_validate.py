from unittest.mock import MagicMock

from app.validation.validate import validate
from tests.test_validation_judge import _knowledge, _plan


def test_validate_merges_rule_and_judge_issues_and_passes_when_no_critical():
    client = MagicMock()
    client.complete_json.return_value = {"issues": [
        {"severity": "warning", "category": "inconsistency", "location": "plan", "description": "minor"},
    ]}
    report = validate(_plan(), _knowledge(), client=client)
    assert report.passed is True
    assert len(report.issues) == 1


def test_validate_fails_when_any_critical_issue_present():
    client = MagicMock()
    client.complete_json.return_value = {"issues": [
        {"severity": "critical", "category": "hallucination", "location": "period-1", "description": "bad"},
    ]}
    report = validate(_plan(), _knowledge(), client=client)
    assert report.passed is False
