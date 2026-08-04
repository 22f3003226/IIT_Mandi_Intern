# Phase 3: Validation, Publishing, UI, Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Stage 9 (validation), Stage 10 (TKP publishing + PDFs), a
minimal dark-theme frontend, and a single-container HF Spaces deployment,
closing out the Teacher AI Platform assignment.

**Architecture:** New `publish` job type chained off a completed `plan`
job, same pattern Phase 2 used off `document` jobs (`app/jobs/manager.py`
already supports `job_type`/`parent_job_id`). Pipeline: rule-based
validation → LLM-judge validation → merge into `ValidationReport` →
assemble `TeacherKnowledgePackage` → render 3 PDFs → save. Frontend is a
single-page wizard (Vite+React+TS+Tailwind+shadcn) calling the existing
and new REST/SSE endpoints directly, no BFF.

**Tech Stack:** FastAPI, Pydantic v2, SQLite (`JobManager`), OpenRouter
(`OpenRouterClient.complete_json`), fpdf2 (PDF rendering, already a dep),
pytest; React + Vite + TypeScript + Tailwind + shadcn/ui + React Query on
the frontend; Docker on Hugging Face Spaces for deployment.

## Global Constraints

- Grounding: judge LLM call compares generated content against
  `KnowledgeExtract`, not raw document text (FAQ #4). Secondary-source
  pedagogy is not a hallucination.
- Retry pattern: every new LLM-calling function follows the existing
  `MAX_RETRIES = 2`, catch `(LLMResponseError, ValidationError)`,
  schema-repair follow-up prompt pattern (see `app/gaps/generate.py`).
- Job error handling: three-level guard hierarchy (404 → 400 precondition
  → 400 validation) in every new endpoint, matching `app/api/plans.py`.
- A completed `publish` job with `ValidationReport.passed=False` is NOT a
  pipeline failure — only unexpected exceptions set `status="failed"`.
- `fpdf2` moves from `[dependency-groups].dev` to `[project].dependencies`
  in `pyproject.toml` (Task 5) — it's runtime code now.
- Frontend: dark theme by default, no router, no auth, no job-history
  list. Job id lives in a URL query param.
- HF Spaces requires the container to listen on port 7860.

---

### Task 1: Publishing schemas

**Files:**
- Create: `app/schemas/publishing.py`
- Test: `tests/test_schemas_publishing.py`

**Interfaces:**
- Produces: `ValidationIssue(severity: str, category: str, location: str, description: str)`,
  `ValidationReport(issues: list[ValidationIssue], passed: bool)`,
  `TeacherKnowledgePackage(job_id: str, source_job_id: str, plan_job_id: str, classification: ClassificationResult, knowledge: KnowledgeExtract, teaching_plan: TeachingPlan, validation_report: ValidationReport)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas_publishing.py
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import TeacherKnowledgePackage, ValidationIssue, ValidationReport


def _classification():
    return ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                 topic="Motion", chapter="Laws", category="STEM", language="English")


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    return KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                             definitions=[item], formulae=[item], keywords=[item], examples=[item],
                             applications=[item], misconceptions=[item])


def test_validation_report_passed_true_with_no_issues():
    report = ValidationReport(issues=[], passed=True)
    assert report.passed is True
    assert report.issues == []


def test_teacher_knowledge_package_round_trips_through_json():
    report = ValidationReport(
        issues=[ValidationIssue(severity="warning", category="missing_objective",
                                 location="period-1", description="No coverage for X")],
        passed=True,
    )
    plan = TeachingPlan(job_id="plan-1", source_job_id="doc-1", periods=[], gap_analysis=[])
    tkp = TeacherKnowledgePackage(
        job_id="publish-1", source_job_id="doc-1", plan_job_id="plan-1",
        classification=_classification(), knowledge=_knowledge(),
        teaching_plan=plan, validation_report=report,
    )
    restored = TeacherKnowledgePackage.model_validate_json(tkp.model_dump_json())
    assert restored.validation_report.issues[0].category == "missing_objective"
    assert restored.plan_job_id == "plan-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas_publishing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.publishing'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/schemas/publishing.py
from pydantic import BaseModel

from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract
from app.schemas.planning import TeachingPlan


class ValidationIssue(BaseModel):
    severity: str  # "critical" | "warning" | "info"
    category: str  # "hallucination" | "missing_objective" | "inconsistency" | "schema"
    location: str  # e.g. "period-3" or "plan"
    description: str


class ValidationReport(BaseModel):
    issues: list[ValidationIssue]
    passed: bool


class TeacherKnowledgePackage(BaseModel):
    job_id: str
    source_job_id: str
    plan_job_id: str
    classification: ClassificationResult
    knowledge: KnowledgeExtract
    teaching_plan: TeachingPlan
    validation_report: ValidationReport
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schemas_publishing.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/schemas/publishing.py tests/test_schemas_publishing.py
git commit -m "feat: add publishing schemas (ValidationReport, TeacherKnowledgePackage)"
```

---

### Task 2: Rule-based validation (Stage 9a)

**Files:**
- Create: `app/validation/__init__.py` (empty)
- Create: `app/validation/rules.py`
- Test: `tests/test_validation_rules.py`

**Interfaces:**
- Consumes: `TeachingPlan` (`app/schemas/planning.py`, has `.periods: list[PeriodPackage]` each with `.plan.objectives: list[str]`, `.plan.concepts_covered: list[str]`, `.plan.title: str`, `.content.teacher_script` etc.)
- Produces: `check_rules(plan: TeachingPlan) -> list[ValidationIssue]` (from `app.schemas.publishing`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validation_rules.py
from app.schemas.extraction import ConceptItem, SourceRef
from app.schemas.planning import Activity, Assessment, PeriodContent, PeriodPackage, PeriodPlan, TeachingPlan
from app.validation.rules import check_rules


def _package(period_no=1, title="Intro", objectives=None, concepts_covered=None,
             teacher_script="script"):
    plan = PeriodPlan(period_no=period_no, duration_min=40, title=title,
                       objectives=objectives if objectives is not None else ["Explain inertia"],
                       concepts_covered=concepts_covered if concepts_covered is not None else ["Inertia"],
                       sequencing_notes="notes")
    content = PeriodContent(entry_ticket="e", teacher_script=teacher_script, blackboard_notes="b",
                             checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
                             grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))])
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"], numerical=["q"],
                             answer_key="k", rubric="r")
    return PeriodPackage(plan=plan, content=content, activities=[], assessment=assessment)


def test_clean_plan_produces_no_issues():
    plan = TeachingPlan(job_id="j", source_job_id="s", periods=[_package()], gap_analysis=[])
    assert check_rules(plan) == []


def test_period_with_no_objectives_flagged():
    plan = TeachingPlan(job_id="j", source_job_id="s", periods=[_package(objectives=[])], gap_analysis=[])
    issues = check_rules(plan)
    assert any(i.category == "missing_objective" and i.location == "period-1" for i in issues)


def test_duplicate_period_titles_flagged():
    plan = TeachingPlan(
        job_id="j", source_job_id="s",
        periods=[_package(period_no=1, title="Intro"), _package(period_no=2, title="Intro")],
        gap_analysis=[],
    )
    issues = check_rules(plan)
    assert any(i.category == "inconsistency" and "duplicate" in i.description.lower() for i in issues)


def test_blank_teacher_script_flagged():
    plan = TeachingPlan(job_id="j", source_job_id="s", periods=[_package(teacher_script="  ")], gap_analysis=[])
    issues = check_rules(plan)
    assert any(i.category == "schema" and i.location == "period-1" for i in issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validation_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.validation'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/validation/rules.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_validation_rules.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/validation/ tests/test_validation_rules.py
git commit -m "feat: add rule-based validation for teaching plans (Stage 9a)"
```

---

### Task 3: LLM-judge validation (Stage 9b) + merged `validate()`

**Files:**
- Create: `app/validation/prompts.py`
- Create: `app/validation/judge.py`
- Modify: `app/validation/rules.py` — no changes, consumed as-is
- Create: `app/validation/validate.py` (merges rules + judge)
- Test: `tests/test_validation_judge.py`
- Test: `tests/test_validation_validate.py`

**Interfaces:**
- Consumes: `check_rules(plan) -> list[ValidationIssue]` (Task 2); `OpenRouterClient.complete_json(model, system_prompt, user_prompt) -> dict`; `settings.openrouter_model_gaps`-style config field (add `openrouter_model_validation`)
- Produces: `judge_plan(plan: TeachingPlan, knowledge: KnowledgeExtract, client=None) -> list[ValidationIssue]`; `validate(plan: TeachingPlan, knowledge: KnowledgeExtract, client=None) -> ValidationReport`

- [ ] **Step 1: Add the new model setting**

```python
# app/config.py — add this line among the other openrouter_model_* fields
    openrouter_model_validation: str = "openai/gpt-4o-mini"
```

- [ ] **Step 2: Write the failing judge test**

```python
# tests/test_validation_judge.py
from unittest.mock import MagicMock

import pytest

from app.llm.openrouter_client import LLMResponseError
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import Activity, Assessment, PeriodContent, PeriodPackage, PeriodPlan, TeachingPlan
from app.validation.judge import judge_plan


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    return KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                             definitions=[item], formulae=[item], keywords=[item], examples=[item],
                             applications=[item], misconceptions=[item])


def _plan():
    plan = PeriodPlan(period_no=1, duration_min=40, title="Intro", objectives=["Explain inertia"],
                       concepts_covered=["Inertia"], sequencing_notes="notes")
    content = PeriodContent(entry_ticket="e", teacher_script="s", blackboard_notes="b",
                             checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
                             grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))])
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"], numerical=["q"],
                             answer_key="k", rubric="r")
    package = PeriodPackage(plan=plan, content=content, activities=[], assessment=assessment)
    return TeachingPlan(job_id="j", source_job_id="s", periods=[package], gap_analysis=[])


def _valid_response():
    return {"issues": [
        {"severity": "critical", "category": "hallucination", "location": "period-1",
         "description": "Mentions Newton's Third Law which is not in the source knowledge."},
    ]}


def test_judge_plan_returns_issues():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    issues = judge_plan(_plan(), _knowledge(), client=client)
    assert len(issues) == 1
    assert issues[0].category == "hallucination"


def test_judge_plan_returns_empty_list_when_no_issues():
    client = MagicMock()
    client.complete_json.return_value = {"issues": []}
    issues = judge_plan(_plan(), _knowledge(), client=client)
    assert issues == []


def test_judge_plan_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    issues = judge_plan(_plan(), _knowledge(), client=client)
    assert len(issues) == 1
    assert client.complete_json.call_count == 2


def test_judge_plan_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        judge_plan(_plan(), _knowledge(), client=client)
    assert client.complete_json.call_count == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_validation_judge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.validation.judge'`

- [ ] **Step 4: Write minimal implementation**

```python
# app/validation/prompts.py
SYSTEM_PROMPT = """You are a strict academic fact-checker reviewing a generated teaching plan for a
classroom. You are given the chapter's full knowledge extract (the ONLY approved source of subject
matter facts) and the complete teaching plan generated from it. Check for:
1. Hallucination: any claim, fact, formula, or example in the plan that is NOT traceable to the
   knowledge extract. Teaching strategies, analogies, and activity ideas from general pedagogy are
   fine and must NOT be flagged — only flag new subject-matter facts.
2. Missing coverage: learning objectives or concepts in the knowledge extract that no period
   addresses.
3. Cross-period inconsistency: contradictory statements between periods.
Respond ONLY with a JSON object with exactly one key "issues", an array of objects each with:
severity (string: "critical"/"warning"/"info"), category (string: "hallucination"/
"missing_objective"/"inconsistency"), location (string, e.g. "period-2" or "plan"), description
(string). Return an empty array if you find nothing wrong."""

MAX_CONTEXT_CHARS = 12000


def build_user_prompt(plan: dict, knowledge: dict) -> str:
    return (
        f"Knowledge extract (approved source of facts):\n{str(knowledge)[:MAX_CONTEXT_CHARS]}\n\n"
        f"Generated teaching plan to check:\n{str(plan)[:MAX_CONTEXT_CHARS]}"
    )
```

```python
# app/validation/judge.py
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
```

- [ ] **Step 5: Run judge test to verify it passes**

Run: `uv run pytest tests/test_validation_judge.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Write the failing merge test**

```python
# tests/test_validation_validate.py
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
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_validation_validate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.validation.validate'`

- [ ] **Step 8: Write minimal implementation**

```python
# app/validation/validate.py
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
```

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/test_validation_validate.py tests/test_validation_judge.py -v`
Expected: PASS (6 tests)

- [ ] **Step 10: Commit**

```bash
git add app/config.py app/validation/ tests/test_validation_judge.py tests/test_validation_validate.py
git commit -m "feat: add LLM-judge validation and merged validate() (Stage 9b)"
```

---

### Task 4: Publishing assembly (Stage 10a) + storage

**Files:**
- Create: `app/publishing/__init__.py` (empty)
- Create: `app/publishing/assemble.py`
- Modify: `app/storage/files.py` — add `save_publish_result_json`
- Test: `tests/test_publishing_assemble.py`
- Test: `tests/test_storage_files.py` — add one case (append, don't rewrite existing tests)

**Interfaces:**
- Consumes: `DocumentKnowledgeExtract` (`app/schemas/document_knowledge.py`), `TeachingPlan`, `ValidationReport` (Task 1/3)
- Produces: `assemble_tkp(job_id: str, source_job_id: str, plan_job_id: str, source: DocumentKnowledgeExtract, plan: TeachingPlan, validation_report: ValidationReport) -> TeacherKnowledgePackage`; `save_publish_result_json(storage_dir: str, job_id: str, content: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_publishing_assemble.py
from app.publishing.assemble import assemble_tkp
from app.schemas.classification import ClassificationResult
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import ValidationReport


def test_assemble_tkp_combines_all_inputs():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    knowledge = KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                                  definitions=[item], formulae=[item], keywords=[item], examples=[item],
                                  applications=[item], misconceptions=[item])
    classification = ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                           topic="Motion", chapter="Laws", category="STEM", language="English")
    parsed = ParsedDocument(metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
                             sections=[Section(heading="Intro", text="Body.", page=1)])
    source = DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)
    plan = TeachingPlan(job_id="plan-1", source_job_id="doc-1", periods=[], gap_analysis=[])
    report = ValidationReport(issues=[], passed=True)

    tkp = assemble_tkp(job_id="pub-1", source_job_id="doc-1", plan_job_id="plan-1",
                        source=source, plan=plan, validation_report=report)

    assert tkp.job_id == "pub-1"
    assert tkp.classification.subject == "Physics"
    assert tkp.knowledge.concepts[0].text == "Inertia"
    assert tkp.teaching_plan.job_id == "plan-1"
    assert tkp.validation_report.passed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publishing_assemble.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.publishing'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/publishing/assemble.py
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.planning import TeachingPlan
from app.schemas.publishing import TeacherKnowledgePackage, ValidationReport


def assemble_tkp(
    job_id: str,
    source_job_id: str,
    plan_job_id: str,
    source: DocumentKnowledgeExtract,
    plan: TeachingPlan,
    validation_report: ValidationReport,
) -> TeacherKnowledgePackage:
    return TeacherKnowledgePackage(
        job_id=job_id,
        source_job_id=source_job_id,
        plan_job_id=plan_job_id,
        classification=source.classification,
        knowledge=source.knowledge,
        teaching_plan=plan,
        validation_report=validation_report,
    )
```

```python
# app/storage/files.py — append this function to the existing file
def save_publish_result_json(storage_dir: str, job_id: str, content: str) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "TeacherKnowledgePackage.json"
    dest_path.write_text(content, encoding="utf-8")
    return str(dest_path)
```

- [ ] **Step 4: Add a storage test case**

```python
# tests/test_storage_files.py — append this test to the existing file
def test_save_publish_result_json_writes_file(tmp_path):
    from app.storage.files import save_publish_result_json

    path = save_publish_result_json(str(tmp_path), "job-1", '{"job_id": "job-1"}')
    assert Path(path).name == "TeacherKnowledgePackage.json"
    assert Path(path).read_text() == '{"job_id": "job-1"}'
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_publishing_assemble.py tests/test_storage_files.py -v`
Expected: PASS (all storage tests + 1 new assemble test)

- [ ] **Step 6: Commit**

```bash
git add app/publishing/ app/storage/files.py tests/test_publishing_assemble.py tests/test_storage_files.py
git commit -m "feat: assemble TeacherKnowledgePackage (Stage 10a)"
```

---

### Task 5: PDF generation (Stage 10b)

**Files:**
- Modify: `pyproject.toml` — move `fpdf2` from `[dependency-groups].dev` to `[project].dependencies`
- Create: `app/publishing/pdf.py`
- Test: `tests/test_publishing_pdf.py`

**Interfaces:**
- Consumes: `TeacherKnowledgePackage` (Task 1)
- Produces: `render_lesson_plan_pdf(tkp: TeacherKnowledgePackage) -> bytes`, `render_teacher_guide_pdf(tkp: TeacherKnowledgePackage) -> bytes`, `render_assessment_book_pdf(tkp: TeacherKnowledgePackage) -> bytes`

- [ ] **Step 1: Move the dependency**

Edit `pyproject.toml`: remove `"fpdf2>=2.8.7",` from `[dependency-groups].dev` and add it to `[project].dependencies` (alphabetical, after `"fastapi>=0.141.1",`):

```toml
dependencies = [
    "fastapi>=0.141.1",
    "fpdf2>=2.8.7",
    "httpx>=0.28.1",
    ...
]
```

Run: `uv sync`
Expected: lockfile updates, no errors.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_publishing_pdf.py
from app.publishing.pdf import render_assessment_book_pdf, render_lesson_plan_pdf, render_teacher_guide_pdf
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import Activity, Assessment, PeriodContent, PeriodPackage, PeriodPlan, TeachingPlan
from app.schemas.publishing import TeacherKnowledgePackage, ValidationReport


def _tkp():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    knowledge = KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                                  definitions=[item], formulae=[item], keywords=[item], examples=[item],
                                  applications=[item], misconceptions=[item])
    classification = ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                           topic="Motion", chapter="Laws of Motion", category="STEM",
                                           language="English")
    plan_item = PeriodPlan(period_no=1, duration_min=40, title="Intro", objectives=["Explain inertia"],
                            concepts_covered=["Inertia"], sequencing_notes="First period.")
    content = PeriodContent(entry_ticket="e", teacher_script="Explain that objects resist changes in motion.",
                             blackboard_notes="F = m*a", checkpoint_questions=["What is inertia?"],
                             exit_ticket="x", homework="h", mentor_moment="Newton once said...",
                             grounded_notes=[item])
    activities = [Activity(type="demo", duration_min=10, materials=["ball"],
                            teacher_instructions="Roll the ball", success_criteria="Predicts motion")]
    assessment = Assessment(mcqs=["What is inertia?"], short_answer=["Define inertia"],
                             long_answer=["Explain inertia with an example"], numerical=["Calc F=ma"],
                             answer_key="See above", rubric="1 point each")
    package = PeriodPackage(plan=plan_item, content=content, activities=activities, assessment=assessment)
    plan = TeachingPlan(job_id="plan-1", source_job_id="doc-1", periods=[package], gap_analysis=[])
    report = ValidationReport(issues=[], passed=True)
    return TeacherKnowledgePackage(job_id="pub-1", source_job_id="doc-1", plan_job_id="plan-1",
                                    classification=classification, knowledge=knowledge,
                                    teaching_plan=plan, validation_report=report)


def test_render_lesson_plan_pdf_produces_nonempty_bytes():
    pdf_bytes = render_lesson_plan_pdf(_tkp())
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 100


def test_render_teacher_guide_pdf_produces_nonempty_bytes():
    pdf_bytes = render_teacher_guide_pdf(_tkp())
    assert pdf_bytes.startswith(b"%PDF")


def test_render_assessment_book_pdf_produces_nonempty_bytes():
    pdf_bytes = render_assessment_book_pdf(_tkp())
    assert pdf_bytes.startswith(b"%PDF")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_publishing_pdf.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.publishing.pdf'`

- [ ] **Step 4: Write minimal implementation**

```python
# app/publishing/pdf.py
from fpdf import FPDF

from app.schemas.publishing import TeacherKnowledgePackage


def _new_pdf(title: str, tkp: TeacherKnowledgePackage) -> FPDF:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, title)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 8, f"{tkp.classification.subject} | Grade {tkp.classification.grade} | "
                          f"{tkp.classification.chapter}")
    pdf.ln(4)
    return pdf


def _heading(pdf: FPDF, text: str) -> None:
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 8, text)
    pdf.set_font("Helvetica", "", 11)


def render_lesson_plan_pdf(tkp: TeacherKnowledgePackage) -> bytes:
    pdf = _new_pdf("Lesson Plan", tkp)
    for package in tkp.teaching_plan.periods:
        period = package.plan
        _heading(pdf, f"Period {period.period_no}: {period.title} ({period.duration_min} min)")
        pdf.multi_cell(0, 7, "Objectives: " + "; ".join(period.objectives))
        pdf.multi_cell(0, 7, "Concepts covered: " + "; ".join(period.concepts_covered))
        pdf.multi_cell(0, 7, "Sequencing notes: " + period.sequencing_notes)
        pdf.ln(4)
    return bytes(pdf.output())


def render_teacher_guide_pdf(tkp: TeacherKnowledgePackage) -> bytes:
    pdf = _new_pdf("Teacher Guide", tkp)
    for package in tkp.teaching_plan.periods:
        period, content = package.plan, package.content
        _heading(pdf, f"Period {period.period_no}: {period.title}")
        pdf.multi_cell(0, 7, "Entry Ticket: " + content.entry_ticket)
        pdf.multi_cell(0, 7, "Teacher Script: " + content.teacher_script)
        pdf.multi_cell(0, 7, "Blackboard Notes: " + content.blackboard_notes)
        for activity in package.activities:
            pdf.multi_cell(0, 7, f"Activity ({activity.type}, {activity.duration_min} min): "
                                  f"{activity.teacher_instructions}")
        pdf.multi_cell(0, 7, "Exit Ticket: " + content.exit_ticket)
        pdf.multi_cell(0, 7, "Homework: " + content.homework)
        pdf.multi_cell(0, 7, "Mentor Moment: " + content.mentor_moment)
        pdf.ln(4)
    return bytes(pdf.output())


def render_assessment_book_pdf(tkp: TeacherKnowledgePackage) -> bytes:
    pdf = _new_pdf("Assessment Book", tkp)
    for package in tkp.teaching_plan.periods:
        period, assessment = package.plan, package.assessment
        _heading(pdf, f"Period {period.period_no}: {period.title}")
        pdf.multi_cell(0, 7, "MCQs: " + "; ".join(assessment.mcqs))
        pdf.multi_cell(0, 7, "Short Answer: " + "; ".join(assessment.short_answer))
        pdf.multi_cell(0, 7, "Long Answer: " + "; ".join(assessment.long_answer))
        pdf.multi_cell(0, 7, "Numerical: " + "; ".join(assessment.numerical))
        pdf.multi_cell(0, 7, "Answer Key: " + assessment.answer_key)
        pdf.multi_cell(0, 7, "Rubric: " + assessment.rubric)
        pdf.ln(4)
    return bytes(pdf.output())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_publishing_pdf.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock app/publishing/pdf.py tests/test_publishing_pdf.py
git commit -m "feat: render Lesson Plan / Teacher Guide / Assessment Book PDFs (Stage 10b)"
```

---

### Task 6: Publish pipeline orchestration

**Files:**
- Create: `app/jobs/pipeline_publish.py`
- Modify: `app/storage/files.py` — add `save_publish_pdf`
- Test: `tests/test_pipeline_publish.py`

**Interfaces:**
- Consumes: `validate()` (Task 3), `assemble_tkp()` (Task 4), `render_lesson_plan_pdf/render_teacher_guide_pdf/render_assessment_book_pdf` (Task 5), `save_publish_result_json` (Task 4), `JobManager.update_job(job_id, status=None, stage=None, progress=None, result_path=None, error=None)`
- Produces: `async def run_publish_pipeline(job_manager: JobManager, storage_dir: str, job_id: str, source: DocumentKnowledgeExtract, plan: TeachingPlan, plan_job_id: str, source_job_id: str) -> None`; `save_publish_pdf(storage_dir: str, job_id: str, kind: str, content: bytes) -> str`

- [ ] **Step 1: Add PDF storage helper**

```python
# app/storage/files.py — append
def save_publish_pdf(storage_dir: str, job_id: str, kind: str, content: bytes) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{kind}.pdf"
    dest_path.write_bytes(content)
    return str(dest_path)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_pipeline_publish.py
import asyncio
from pathlib import Path
from unittest.mock import patch

from app.jobs.manager import JobManager
from app.jobs.pipeline_publish import run_publish_pipeline
from app.schemas.classification import ClassificationResult
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section
from app.schemas.planning import Activity, Assessment, PeriodContent, PeriodPackage, PeriodPlan, TeachingPlan
from app.schemas.publishing import ValidationReport


def _source():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    knowledge = KnowledgeExtract(learning_objectives=[item], prerequisites=[item], concepts=[item],
                                  definitions=[item], formulae=[item], keywords=[item], examples=[item],
                                  applications=[item], misconceptions=[item])
    classification = ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                           topic="Motion", chapter="Laws", category="STEM", language="English")
    parsed = ParsedDocument(metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
                             sections=[Section(heading="Intro", text="Body.", page=1)])
    return DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)


def _plan():
    plan_item = PeriodPlan(period_no=1, duration_min=40, title="Intro", objectives=["Explain inertia"],
                            concepts_covered=["Inertia"], sequencing_notes="notes")
    content = PeriodContent(entry_ticket="e", teacher_script="s", blackboard_notes="b",
                             checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
                             grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))])
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"], numerical=["q"],
                             answer_key="k", rubric="r")
    package = PeriodPackage(plan=plan_item, content=content, activities=[], assessment=assessment)
    return TeachingPlan(job_id="plan-1", source_job_id="doc-1", periods=[package], gap_analysis=[])


def test_run_publish_pipeline_completes_and_writes_all_outputs(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish", parent_job_id=plan_job_id)

    with patch("app.jobs.pipeline_publish.validate") as mock_validate:
        mock_validate.return_value = ValidationReport(issues=[], passed=True)
        asyncio.run(run_publish_pipeline(job_manager, str(tmp_path), job_id, _source(), _plan(),
                                          plan_job_id, source_job_id))

    job = job_manager.get_job(job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert Path(job["result_path"]).name == "TeacherKnowledgePackage.json"
    assert (tmp_path / job_id / "lesson-plan.pdf").exists()
    assert (tmp_path / job_id / "teacher-guide.pdf").exists()
    assert (tmp_path / job_id / "assessment-book.pdf").exists()


def test_run_publish_pipeline_marks_failed_on_stage_error(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish", parent_job_id=plan_job_id)

    with patch("app.jobs.pipeline_publish.validate", side_effect=RuntimeError("boom")):
        asyncio.run(run_publish_pipeline(job_manager, str(tmp_path), job_id, _source(), _plan(),
                                          plan_job_id, source_job_id))

    job = job_manager.get_job(job_id)
    assert job["status"] == "failed"
    assert "boom" in job["error"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_publish.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jobs.pipeline_publish'`

- [ ] **Step 4: Write minimal implementation**

```python
# app/jobs/pipeline_publish.py
import asyncio
import logging

from app.jobs.manager import JobManager
from app.publishing.assemble import assemble_tkp
from app.publishing.pdf import render_assessment_book_pdf, render_lesson_plan_pdf, render_teacher_guide_pdf
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.planning import TeachingPlan
from app.storage.files import save_publish_pdf, save_publish_result_json
from app.validation.validate import validate

logger = logging.getLogger(__name__)


async def run_publish_pipeline(
    job_manager: JobManager,
    storage_dir: str,
    job_id: str,
    source: DocumentKnowledgeExtract,
    plan: TeachingPlan,
    plan_job_id: str,
    source_job_id: str,
) -> None:
    try:
        job_manager.update_job(job_id, status="running", stage="validation", progress=20)
        report = await asyncio.to_thread(validate, plan, source.knowledge)

        job_manager.update_job(job_id, stage="assembling", progress=50)
        tkp = assemble_tkp(job_id=job_id, source_job_id=source_job_id, plan_job_id=plan_job_id,
                            source=source, plan=plan, validation_report=report)

        job_manager.update_job(job_id, stage="rendering-pdfs", progress=70)
        for kind, renderer in (
            ("lesson-plan", render_lesson_plan_pdf),
            ("teacher-guide", render_teacher_guide_pdf),
            ("assessment-book", render_assessment_book_pdf),
        ):
            pdf_bytes = await asyncio.to_thread(renderer, tkp)
            await asyncio.to_thread(save_publish_pdf, storage_dir, job_id, kind, pdf_bytes)

        job_manager.update_job(job_id, stage="packaging", progress=95)
        result_path = await asyncio.to_thread(
            save_publish_result_json, storage_dir, job_id, tkp.model_dump_json(indent=2)
        )

        job_manager.update_job(job_id, status="completed", stage="done", progress=100, result_path=result_path)
    except Exception as exc:
        logger.exception("Publish pipeline failed for job %s", job_id)
        job_manager.update_job(job_id, status="failed", error=str(exc))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_publish.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add app/jobs/pipeline_publish.py app/storage/files.py tests/test_pipeline_publish.py
git commit -m "feat: orchestrate publish pipeline (validate -> assemble -> PDFs)"
```

---

### Task 7: Publish API endpoints

**Files:**
- Create: `app/api/publish.py`
- Modify: `app/main.py` — register the new router
- Test: `tests/test_api_publish.py`

**Interfaces:**
- Consumes: `run_publish_pipeline()` (Task 6), `deps.job_manager` (`app/deps.py`), `JobStatusResponse` (`app/schemas/job.py`)
- Produces: `POST /jobs/{plan_job_id}/publish`, `GET /jobs/{job_id}/publish`, `GET /jobs/{job_id}/publish/pdf/{kind}`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_publish.py
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.main import app

VALID_TKP = {
    "job_id": "pub-1", "source_job_id": "doc-1", "plan_job_id": "plan-1",
    "classification": {"subject": "Physics", "grade": "9", "difficulty": "medium", "topic": "Motion",
                        "chapter": "Laws", "category": "STEM", "language": "English"},
    "knowledge": {k: [] for k in ["learning_objectives", "prerequisites", "concepts", "definitions",
                                   "formulae", "keywords", "examples", "applications", "misconceptions"]},
    "teaching_plan": {"job_id": "plan-1", "source_job_id": "doc-1", "periods": [], "gap_analysis": []},
    "validation_report": {"issues": [], "passed": True},
}


def test_create_publish_404_for_unknown_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    client = TestClient(app)
    response = client.post("/jobs/does-not-exist/publish")
    assert response.status_code == 404


def test_create_publish_400_when_plan_job_not_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)

    client = TestClient(app)
    response = client.post(f"/jobs/{plan_job_id}/publish")
    assert response.status_code == 400


def test_create_publish_400_when_job_is_not_a_plan_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(doc_job_id, status="completed", result_path="/tmp/x.json")

    client = TestClient(app)
    response = client.post(f"/jobs/{doc_job_id}/publish")
    assert response.status_code == 400


def test_create_publish_starts_pipeline_for_completed_plan_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))

    doc_result = tmp_path / "DocumentKnowledgeExtract.json"
    doc_result.write_text(json.dumps({
        "parsed_document": {"metadata": {"source_filename": "x.txt", "format": "txt", "page_count": 1},
                             "sections": [{"heading": "Intro", "text": "Body.", "page": 1}],
                             "tables": [], "figures": [], "equations": []},
        "classification": {"subject": "Physics", "grade": "9", "difficulty": "medium", "topic": "Motion",
                            "chapter": "Laws", "category": "STEM", "language": "English"},
        "knowledge": {k: [] for k in ["learning_objectives", "prerequisites", "concepts", "definitions",
                                       "formulae", "keywords", "examples", "applications", "misconceptions"]},
    }))
    plan_result = tmp_path / "TeachingPlan.json"
    plan_result.write_text(json.dumps({"job_id": "plan-1", "source_job_id": "doc-1", "periods": [],
                                        "gap_analysis": []}))

    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(doc_job_id, status="completed", result_path=str(doc_result))
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)
    deps.job_manager.update_job(plan_job_id, status="completed", result_path=str(plan_result))

    with patch("app.api.publish.run_publish_pipeline", new=AsyncMock()):
        client = TestClient(app)
        response = client.post(f"/jobs/{plan_job_id}/publish")

    assert response.status_code == 200
    publish_job_id = response.json()["id"]
    publish_job = deps.job_manager.get_job(publish_job_id)
    assert publish_job["job_type"] == "publish"
    assert publish_job["parent_job_id"] == plan_job_id


def test_get_publish_returns_tkp_json_when_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    result_path = tmp_path / "TeacherKnowledgePackage.json"
    result_path.write_text(json.dumps(VALID_TKP))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)
    publish_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish",
                                                  parent_job_id=plan_job_id)
    deps.job_manager.update_job(publish_job_id, status="completed", result_path=str(result_path))

    client = TestClient(app)
    response = client.get(f"/jobs/{publish_job_id}/publish")
    assert response.status_code == 200
    assert response.json()["job_id"] == "pub-1"


def test_get_publish_pdf_streams_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_dir = tmp_path / "files" / "pub-1"
    job_dir.mkdir(parents=True)
    pdf_path = job_dir / "lesson-plan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)
    publish_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish",
                                                  parent_job_id=plan_job_id, job_id="pub-1")
    deps.job_manager.update_job(publish_job_id, status="completed", result_path=str(job_dir / "TeacherKnowledgePackage.json"))

    client = TestClient(app)
    response = client.get(f"/jobs/{publish_job_id}/publish/pdf/lesson-plan")
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 fake"


def test_get_publish_pdf_400_for_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    doc_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=doc_job_id)
    publish_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="publish",
                                                  parent_job_id=plan_job_id)
    deps.job_manager.update_job(publish_job_id, status="completed",
                                 result_path=str(tmp_path / "files" / publish_job_id / "TeacherKnowledgePackage.json"))

    client = TestClient(app)
    response = client.get(f"/jobs/{publish_job_id}/publish/pdf/not-a-kind")
    assert response.status_code == 400
```

Note: `deps.job_manager.create_job` needs a `job_id` override for the
streaming test to control the storage subdirectory name — confirm
`app/jobs/manager.py`'s `create_job(file_path, job_id=None, job_type=..., parent_job_id=...)`
signature already supports this (it does, see `app/jobs/manager.py:41-57`).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_publish.py -v`
Expected: FAIL — router / endpoints don't exist (404s where 200/400 expected, or `ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# app/api/publish.py
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app import deps
from app.config import settings
from app.jobs.pipeline_publish import run_publish_pipeline
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.job import JobStatusResponse
from app.schemas.planning import TeachingPlan

router = APIRouter()

_background_tasks: set[asyncio.Task] = set()
_PDF_KINDS = {"lesson-plan", "teacher-guide", "assessment-book"}


def _to_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        id=job["id"], status=job["status"], stage=job["stage"],
        progress=job["progress"], error=job["error"], result_path=job["result_path"],
    )


@router.post("/jobs/{plan_job_id}/publish", response_model=JobStatusResponse)
async def create_publish(plan_job_id: str) -> JobStatusResponse:
    plan_job = deps.job_manager.get_job(plan_job_id)
    if plan_job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if plan_job["job_type"] != "plan":
        raise HTTPException(status_code=400, detail="Source job is not a plan job")
    if plan_job["status"] != "completed" or not plan_job["result_path"]:
        raise HTTPException(status_code=400, detail="Plan job result not available")

    source_job = deps.job_manager.get_job(plan_job["parent_job_id"])
    if source_job is None or source_job["status"] != "completed" or not source_job["result_path"]:
        raise HTTPException(status_code=400, detail="Source document job result not available")

    try:
        plan_raw = await asyncio.to_thread(Path(plan_job["result_path"]).read_text)
        plan = TeachingPlan.model_validate(json.loads(plan_raw))
        source_raw = await asyncio.to_thread(Path(source_job["result_path"]).read_text)
        source = DocumentKnowledgeExtract.model_validate(json.loads(source_raw))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Plan or source job result is unreadable or invalid") from exc

    publish_job_id = deps.job_manager.create_job(
        file_path=plan_job["file_path"], job_type="publish", parent_job_id=plan_job_id
    )
    task = asyncio.create_task(
        run_publish_pipeline(deps.job_manager, settings.storage_dir, publish_job_id, source, plan,
                              plan_job_id, source_job["id"])
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return _to_response(deps.job_manager.get_job(publish_job_id))


@router.get("/jobs/{job_id}/publish")
async def get_publish(job_id: str):
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["job_type"] != "publish":
        raise HTTPException(status_code=400, detail="Job is not a publish job")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Publish job is not completed")
    raw = await asyncio.to_thread(Path(job["result_path"]).read_text)
    return json.loads(raw)


@router.get("/jobs/{job_id}/publish/pdf/{kind}")
async def get_publish_pdf(job_id: str, kind: str):
    if kind not in _PDF_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown PDF kind: {kind!r}")
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["job_type"] != "publish":
        raise HTTPException(status_code=400, detail="Job is not a publish job")
    if job["status"] != "completed" or not job["result_path"]:
        raise HTTPException(status_code=400, detail="Publish job is not completed")
    pdf_path = Path(job["result_path"]).parent / f"{kind}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{kind}.pdf")
```

```python
# app/main.py — replace the whole file
from fastapi import FastAPI

from app.api import documents, jobs, plans, publish

app = FastAPI(title="Teacher AI Platform")
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(plans.router)
app.include_router(publish.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_publish.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full backend suite**

Run: `uv run pytest -v`
Expected: PASS, all tests (existing + new) green.

- [ ] **Step 6: Commit**

```bash
git add app/api/publish.py app/main.py tests/test_api_publish.py
git commit -m "feat: add publish API endpoints (Stage 9-10 orchestration)"
```

---

### Task 8: Frontend scaffold — dark-theme shell

**Files:**
- Create: `frontend/` (Vite + React + TS project, scaffolded via `npm create vite@latest`)
- Create: `frontend/tailwind.config.ts`, `frontend/src/index.css` (Tailwind + shadcn dark tokens)
- Create: `frontend/src/App.tsx` (shell only — no feature logic yet)
- Create: `frontend/components.json` (shadcn config)

**Interfaces:**
- Produces: a running `npm run dev` shell at `http://localhost:5173` showing an empty dark-themed page with a header/logo — the foundation Task 9/10 build on. No backend calls yet.

- [ ] **Step 1: Scaffold the Vite project**

Run:
```bash
cd /home/prince23/Mandi
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```
Expected: `frontend/` created with a working `package.json`, `src/App.tsx`, `src/main.tsx`.

- [ ] **Step 2: Install Tailwind and shadcn/ui**

Run:
```bash
cd /home/prince23/Mandi/frontend
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm install @tanstack/react-query lucide-react clsx tailwind-merge class-variance-authority
npx shadcn@latest init
```
When `shadcn@latest init` prompts: choose **TypeScript**, base color **Neutral**, CSS variables **yes**. This creates `components.json` and `src/lib/utils.ts`.

Then, using the shadcn mcp tool (already installed), pull the `button`,
`card`, `tabs`, `progress`, `badge` primitives into `frontend/src/components/ui/`
— call the shadcn mcp's component-add tool for each of those 5
components against this project directory. If the mcp tool is
unavailable at execution time, fall back to `npx shadcn@latest add
button card tabs progress badge`.

- [ ] **Step 3: Set dark theme as default and apply `/minimalist-ui` tokens**

```css
/* frontend/src/index.css — replace generated content */
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
}

html {
  @apply dark;
}

body {
  @apply bg-neutral-950 text-neutral-100 antialiased;
  font-family: "Inter", ui-sans-serif, system-ui, sans-serif;
}
```

Edit `frontend/tailwind.config.ts` — set `darkMode: "class"` and content globs to
`["./index.html", "./src/**/*.{ts,tsx}"]` (the `shadcn init` step already
wrote most of this file; only adjust `darkMode` if it isn't already `"class"`).

- [ ] **Step 4: Write the shell**

```tsx
// frontend/src/App.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-neutral-950 text-neutral-100">
        <header className="border-b border-neutral-800 px-6 py-4">
          <h1 className="text-lg font-medium tracking-tight">Teacher AI Platform</h1>
        </header>
        <main className="mx-auto max-w-3xl px-6 py-10">
          <p className="text-neutral-400">Upload a document to generate a Teacher Knowledge Package.</p>
        </main>
      </div>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 5: Verify it runs**

Run: `cd /home/prince23/Mandi/frontend && npm run dev`
Expected: dev server starts on `http://localhost:5173`; open it and confirm a dark page with the header renders (visually check, no automated test for this scaffold step).

Stop the dev server (Ctrl+C) once confirmed.

- [ ] **Step 6: Commit**

```bash
cd /home/prince23/Mandi
git add frontend/
git commit -m "feat: scaffold frontend (Vite+React+TS+Tailwind+shadcn, dark theme)"
```

---

### Task 9: Frontend upload → processing → result flow

**Files:**
- Create: `frontend/src/lib/api.ts` (typed fetch wrappers for the backend)
- Create: `frontend/src/hooks/useJobStream.ts` (SSE progress hook)
- Create: `frontend/src/components/UploadStep.tsx`
- Create: `frontend/src/components/ProcessingStep.tsx`
- Create: `frontend/src/components/ResultStep.tsx`
- Modify: `frontend/src/App.tsx` — wire the 3-step wizard
- Create: `frontend/.env.example` (`VITE_API_BASE_URL=http://localhost:8000`)

**Interfaces:**
- Consumes: backend endpoints from Tasks 6-7 — `POST /jobs` (existing, `app/api/documents.py`, confirm its exact path/field name before writing `api.ts`), `POST /jobs/{id}/plan`, `POST /jobs/{plan_job_id}/publish`, `GET /jobs/{id}/stream` (SSE), `GET /jobs/{id}/publish`, `GET /jobs/{id}/publish/pdf/{kind}`
- Produces: a working end-to-end wizard reachable via `npm run dev`

- [ ] **Step 1: Confirm the upload endpoint contract**

Run: `cat /home/prince23/Mandi/app/api/documents.py`
Read the route path, method, and the multipart field name it expects
(e.g. `file: UploadFile`) — use these exact values in `api.ts` below. Do
not guess; if the field name differs from `file`, adjust the code in
Step 2 to match.

- [ ] **Step 2: Write the API client**

```ts
// frontend/src/lib/api.ts
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface JobStatus {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string | null;
  progress: number;
  error: string | null;
  result_path: string | null;
}

export async function uploadDocument(file: File): Promise<JobStatus> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/jobs`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function createPlan(documentJobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE_URL}/jobs/${documentJobId}/plan`, { method: "POST" });
  if (!res.ok) throw new Error(`Plan creation failed: ${res.status}`);
  return res.json();
}

export async function createPublish(planJobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE_URL}/jobs/${planJobId}/publish`, { method: "POST" });
  if (!res.ok) throw new Error(`Publish creation failed: ${res.status}`);
  return res.json();
}

export async function getPublishResult(publishJobId: string): Promise<unknown> {
  const res = await fetch(`${BASE_URL}/jobs/${publishJobId}/publish`);
  if (!res.ok) throw new Error(`Fetching TKP failed: ${res.status}`);
  return res.json();
}

export function publishPdfUrl(publishJobId: string, kind: "lesson-plan" | "teacher-guide" | "assessment-book") {
  return `${BASE_URL}/jobs/${publishJobId}/publish/pdf/${kind}`;
}
```

Adjust the `uploadDocument` route/field name per what Step 1 found in
`app/api/documents.py` before moving on.

- [ ] **Step 3: Write the SSE progress hook**

```ts
// frontend/src/hooks/useJobStream.ts
import { useEffect, useState } from "react";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface JobStreamEvent {
  stage: string | null;
  progress: number;
  status: string;
}

export function useJobStream(jobId: string | null): JobStreamEvent | null {
  const [event, setEvent] = useState<JobStreamEvent | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const source = new EventSource(`${BASE_URL}/jobs/${jobId}/stream`);
    source.onmessage = (msg) => {
      const data = JSON.parse(msg.data) as JobStreamEvent;
      setEvent(data);
      if (data.status === "completed" || data.status === "failed") source.close();
    };
    return () => source.close();
  }, [jobId]);

  return event;
}
```

- [ ] **Step 4: Write the three step components**

```tsx
// frontend/src/components/UploadStep.tsx
import { useState } from "react";
import { uploadDocument } from "../lib/api";

export function UploadStep({ onUploaded }: { onUploaded: (jobId: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const job = await uploadDocument(file);
      onUploaded(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 p-8 text-center">
      <label className="cursor-pointer text-sm text-neutral-300">
        {busy ? "Uploading..." : "Choose a PDF, DOCX, PPTX, or TXT file"}
        <input type="file" className="hidden" onChange={handleChange} disabled={busy}
               accept=".pdf,.docx,.pptx,.txt" />
      </label>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
    </div>
  );
}
```

```tsx
// frontend/src/components/ProcessingStep.tsx
import { useJobStream } from "../hooks/useJobStream";

export function ProcessingStep({ jobId, label }: { jobId: string; label: string }) {
  const event = useJobStream(jobId);
  const progress = event?.progress ?? 0;
  const stage = event?.stage ?? "starting";

  return (
    <div className="rounded-lg border border-neutral-800 p-8">
      <p className="mb-2 text-sm text-neutral-400">{label}: {stage}</p>
      <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-800">
        <div className="h-full bg-neutral-100 transition-all" style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}
```

```tsx
// frontend/src/components/ResultStep.tsx
import { useQuery } from "@tanstack/react-query";
import { getPublishResult, publishPdfUrl } from "../lib/api";

interface Tkp {
  classification: { subject: string; grade: string; topic: string; chapter: string };
  teaching_plan: { periods: Array<{ plan: { period_no: number; title: string; objectives: string[] } }> };
  validation_report: { passed: boolean; issues: Array<{ severity: string; description: string; location: string }> };
}

export function ResultStep({ publishJobId }: { publishJobId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["publish-result", publishJobId],
    queryFn: () => getPublishResult(publishJobId) as Promise<Tkp>,
  });

  if (isLoading) return <p className="text-neutral-400">Loading package...</p>;
  if (error) return <p className="text-red-400">Failed to load package.</p>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-medium">{data.classification.subject} — {data.classification.chapter}</h2>
        <p className="text-sm text-neutral-400">Grade {data.classification.grade} · {data.classification.topic}</p>
      </div>

      <div className={`rounded-md border px-4 py-3 text-sm ${data.validation_report.passed
        ? "border-emerald-900 bg-emerald-950/40 text-emerald-300"
        : "border-red-900 bg-red-950/40 text-red-300"}`}>
        Validation: {data.validation_report.passed ? "Passed" : "Issues found"}
        {data.validation_report.issues.length > 0 && (
          <ul className="mt-2 list-inside list-disc space-y-1">
            {data.validation_report.issues.map((issue, i) => (
              <li key={i}>[{issue.severity}] {issue.location}: {issue.description}</li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-neutral-300">Periods</h3>
        <ul className="space-y-2">
          {data.teaching_plan.periods.map((p) => (
            <li key={p.plan.period_no} className="rounded-md border border-neutral-800 p-3 text-sm">
              <p className="font-medium">Period {p.plan.period_no}: {p.plan.title}</p>
              <p className="text-neutral-400">{p.plan.objectives.join("; ")}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex gap-3">
        {(["lesson-plan", "teacher-guide", "assessment-book"] as const).map((kind) => (
          <a key={kind} href={publishPdfUrl(publishJobId, kind)} target="_blank" rel="noreferrer"
             className="rounded-md border border-neutral-700 px-3 py-2 text-sm hover:bg-neutral-900">
            Download {kind.replace("-", " ")}
          </a>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire the wizard in App.tsx**

```tsx
// frontend/src/App.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { createPlan, createPublish } from "./lib/api";
import { UploadStep } from "./components/UploadStep";
import { ProcessingStep } from "./components/ProcessingStep";
import { ResultStep } from "./components/ResultStep";
import { useJobStream } from "./hooks/useJobStream";

const queryClient = new QueryClient();

type Stage = "upload" | "parsing" | "planning" | "publishing" | "result";

function Wizard() {
  const [stage, setStage] = useState<Stage>("upload");
  const [documentJobId, setDocumentJobId] = useState<string | null>(
    new URLSearchParams(window.location.search).get("job")
  );
  const [planJobId, setPlanJobId] = useState<string | null>(null);
  const [publishJobId, setPublishJobId] = useState<string | null>(null);

  const documentEvent = useJobStream(stage === "parsing" ? documentJobId : null);
  const planEvent = useJobStream(stage === "planning" ? planJobId : null);

  useEffect(() => {
    if (documentJobId && stage === "upload") setStage("parsing");
  }, [documentJobId, stage]);

  useEffect(() => {
    if (stage === "parsing" && documentEvent?.status === "completed" && documentJobId) {
      createPlan(documentJobId).then((job) => {
        setPlanJobId(job.id);
        setStage("planning");
      });
    }
  }, [stage, documentEvent, documentJobId]);

  useEffect(() => {
    if (stage === "planning" && planEvent?.status === "completed" && planJobId) {
      createPublish(planJobId).then((job) => {
        setPublishJobId(job.id);
        window.history.replaceState(null, "", `?job=${job.id}`);
        setStage("publishing");
      });
    }
  }, [stage, planEvent, planJobId]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      {stage === "upload" && <UploadStep onUploaded={setDocumentJobId} />}
      {stage === "parsing" && documentJobId && <ProcessingStep jobId={documentJobId} label="Analyzing document" />}
      {stage === "planning" && planJobId && <ProcessingStep jobId={planJobId} label="Building teaching plan" />}
      {stage === "publishing" && publishJobId && <PublishGate publishJobId={publishJobId} onDone={() => setStage("result")} />}
      {stage === "result" && publishJobId && <ResultStep publishJobId={publishJobId} />}
    </div>
  );
}

function PublishGate({ publishJobId, onDone }: { publishJobId: string; onDone: () => void }) {
  const event = useJobStream(publishJobId);
  useEffect(() => {
    if (event?.status === "completed") onDone();
  }, [event, onDone]);
  return <ProcessingStep jobId={publishJobId} label="Validating and packaging" />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-neutral-950 text-neutral-100">
        <header className="border-b border-neutral-800 px-6 py-4">
          <h1 className="text-lg font-medium tracking-tight">Teacher AI Platform</h1>
        </header>
        <main>
          <Wizard />
        </main>
      </div>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 6: Manual end-to-end check**

Run backend: `cd /home/prince23/Mandi && uv run uvicorn app.main:app --reload`
Run frontend: `cd /home/prince23/Mandi/frontend && cp .env.example .env && npm run dev`
Open `http://localhost:5173`, upload a small `.txt` file, and confirm the
wizard progresses through parsing → planning → publishing → result
without console errors, ending on the Result screen with periods,
validation report, and 3 working PDF download links.

If `OPENROUTER_API_KEY` isn't set in the backend's `.env`, this will fail
at the LLM call stages — that's expected without a live key; note it and
move on, the automated pytest suite already covers pipeline logic with
mocked LLM calls.

- [ ] **Step 7: Run `/ui-ux-pro-max`, `/gpt-taste`, and `/impeccable` passes on the Result screen**

Invoke `/ui-ux-pro-max` first against `frontend/src/components/ResultStep.tsx`
and `frontend/src/App.tsx` for layout/typography/color/accessibility
guidance (dark theme, editorial minimalist direction), then `/gpt-taste`,
then `/impeccable` to catch anti-slop issues. Apply any concrete fixes
they surface (spacing, generic card-soup patterns, contrast issues),
re-run Step 6 to confirm it still works after changes.

- [ ] **Step 8: Commit**

```bash
cd /home/prince23/Mandi
git add frontend/
git commit -m "feat: wire upload -> processing -> result wizard to backend API"
```

---

### Task 10: Dockerfile, static serving, README, deploy

**Files:**
- Modify: `app/main.py` — mount built frontend as static files
- Create: `Dockerfile`
- Create: `.dockerignore`
- Modify: `README.md` — architecture diagram, setup, orchestration explanation, HF Spaces deploy steps
- Modify: `.env.example` (if present) or create one — document required env vars

**Interfaces:**
- Consumes: `frontend/dist/` (built by Task 8/9's `npm run build`), all backend routers (Tasks 1-7)
- Produces: a single container serving the frontend at `/` and the API at its existing paths, listening on port 7860

- [ ] **Step 1: Mount static files in main.py**

```python
# app/main.py — add static mount, keep API routers registered first so they take priority
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import documents, jobs, plans, publish

app = FastAPI(title="Teacher AI Platform")
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(plans.router)
app.include_router(publish.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
```

The `if _frontend_dist.exists()` guard keeps `uv run pytest` and local
`uvicorn --reload` working without a frontend build present — only the
Docker image (Step 3) has `frontend/dist/` baked in.

- [ ] **Step 2: Run the backend suite once more to confirm the mount doesn't break existing routes**

Run: `uv run pytest -v`
Expected: PASS, all tests green (the static mount only activates when `frontend/dist/` exists, which it won't in the test environment unless a previous local `npm run build` was run — if it was, confirm `/health` and `/jobs/...` routes still resolve ahead of the catch-all).

- [ ] **Step 3: Write the Dockerfile**

```dockerfile
# Dockerfile
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app/ ./app/
COPY --from=frontend-build /frontend/dist ./frontend/dist
ENV STORAGE_DIR=/app/storage/files
ENV DB_PATH=/app/storage/app.db
EXPOSE 7860
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

- [ ] **Step 4: Write .dockerignore**

```
# .dockerignore
frontend/node_modules
frontend/dist
.venv
__pycache__
*.pyc
storage/
.git
.pytest_cache
```

- [ ] **Step 5: Build and smoke-test the image locally**

Run:
```bash
cd /home/prince23/Mandi
docker build -t teacher-ai-platform .
docker run --rm -p 7860:7860 -e OPENROUTER_API_KEY=<your-key> teacher-ai-platform
```
Expected: container starts, `curl http://localhost:7860/health` returns
`{"status": "ok"}`, and `http://localhost:7860/` in a browser shows the
frontend shell. Stop the container (Ctrl+C) once confirmed.

If Docker isn't available in this environment, note that and skip to
Step 6 — the Dockerfile is still correct for HF Spaces' own build step.

- [ ] **Step 6: Write README updates**

Add these sections to `README.md` (keep whatever setup content already
exists; extend, don't replace, unless it's stale):

```markdown
## Architecture

\`\`\`mermaid
graph LR
  U[Client / Frontend] -->|POST /jobs| A[FastAPI]
  A --> P1[Stage 1-3: Document Intelligence]
  P1 -->|POST /jobs/id/plan| P2[Stage 4-8: Planning & Generation]
  P2 -->|POST /jobs/id/publish| P3[Stage 9-10: Validation & Publishing]
  P3 --> DB[(SQLite JobManager)]
  P3 --> FS[(File storage: JSON + PDFs)]
  P1 & P2 & P3 -.->|OpenRouter LLM calls| LLM[(OpenRouter)]
\`\`\`

Each stage is a Python package (`app/classification/`, `app/extraction/`,
`app/planning/`, `app/content/`, `app/activities/`, `app/assessment/`,
`app/gaps/`, `app/validation/`, `app/publishing/`) sharing one pattern:
an LLM call with `MAX_RETRIES=2` and a schema-repair follow-up prompt on
invalid JSON. Jobs are chained via `job_type`/`parent_job_id` in
`app/jobs/manager.py` (`document` → `plan` → `publish`); each stage
reports progress into SQLite, streamed to the client over
`GET /jobs/{id}/stream` (SSE).

Orchestration pattern: custom sequential pipeline functions
(`app/jobs/pipeline*.py`), not a third-party agent framework — chosen for
transparency and testability (every stage is independently mockable in
`tests/`).

## Local setup

\`\`\`bash
uv sync
cp .env.example .env  # set OPENROUTER_API_KEY
uv run uvicorn app.main:app --reload

cd frontend
npm install
cp .env.example .env
npm run dev
\`\`\`

## Deployment (Hugging Face Spaces)

1. Create a new Space, SDK = **Docker**.
2. Push this repo to the Space's git remote (`git push hf main`).
3. Set `OPENROUTER_API_KEY` as a Space secret (Settings → Repository secrets).
4. The Space builds `Dockerfile` and serves on port 7860 automatically.
```

- [ ] **Step 7: Commit**

```bash
cd /home/prince23/Mandi
git add app/main.py Dockerfile .dockerignore README.md
git commit -m "feat: add Docker deployment, static frontend serving, and README updates"
```

---

## Post-plan verification

- [ ] Run `uv run pytest -v` from repo root — full backend suite green.
- [ ] Run `npm run build` in `frontend/` — production build succeeds with no TypeScript errors.
- [ ] Manually walk the wizard end-to-end against a locally running backend with a real `OPENROUTER_API_KEY` (Task 9 Step 6, repeated with a real key this time) and confirm all 3 PDFs download correctly.
- [ ] Deploy to Hugging Face Spaces per Task 10 Step 6's instructions and confirm the live URL serves both frontend and API.
