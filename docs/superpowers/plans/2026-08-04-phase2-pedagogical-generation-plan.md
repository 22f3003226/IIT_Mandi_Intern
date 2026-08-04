# Phase 2: Pedagogical Planning & Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Stages 4-8 (Teaching Planner, Classroom Content Generation, Activity Generation, Assessment Generation, Learning Gap Analysis) on top of the existing Phase 1 pipeline, producing a `TeachingPlan.json` per completed Phase 1 job.

**Architecture:** One new Pydantic-schema-validated OpenRouter call per stage, mirroring Phase 1's `classification`/`extraction` pattern exactly (system prompt + user prompt builder + retry-on-invalid-JSON loop capped at `MAX_RETRIES = 2`). Stages 5-7 run once per period, sequentially. A new `jobs/pipeline_plan.py` orchestrates all five stages and updates job progress at each step, reusing the existing `JobManager` (SQLite) and SSE endpoint unmodified. Two new FastAPI routes (`POST /jobs/{id}/plan`, `GET /jobs/{id}/plan`) plus one generic addition to the existing jobs router (`GET /jobs/{id}/result`).

**Tech Stack:** Same as Phase 1 — FastAPI, Pydantic v2, `httpx` (via `OpenRouterClient`), SQLite, `uv`, pytest.

## Global Constraints

- Every stage's LLM call schema-validates the response and retries up to `MAX_RETRIES = 2` times with a schema-repair follow-up prompt on `LLMResponseError` or `ValidationError`, exactly like `app/classification/classify.py` and `app/extraction/extract.py`. On exhausting retries, re-raise the last error — the pipeline's `except Exception` catches it and marks the job `failed`.
- Every stage receives the full `KnowledgeExtract` and/or `ClassificationResult` as grounding context. System prompts must state: outside knowledge may only shape pedagogy (analogies, activities, teaching strategy), never introduce new subject matter beyond the source extract.
- Reuse `app.schemas.extraction.SourceRef` and `ConceptItem` for any new schema field that carries a traceable fact — do not redefine them.
- No parallel LLM calls across periods — periods run sequentially in a `for` loop (matches the approved design's "one call per period, sequential" decision).
- All new modules follow the existing package-per-stage layout (`app/planning/`, `app/content/`, `app/activities/`, `app/assessment/`, `app/gaps/`), each with `prompts.py` + one module with the stage's callable, mirroring `app/classification/{prompts.py,classify.py}`.
- `uv run pytest` must stay green after every task.
- No live OpenRouter calls in tests — mock `OpenRouterClient.complete_json` exactly as Phase 1's contract tests do.

---

### Task 1: Config, schemas, storage, and JobManager foundation

**Files:**
- Modify: `app/config.py`
- Create: `app/schemas/planning.py`
- Modify: `app/jobs/manager.py`
- Modify: `app/storage/files.py`
- Test: `tests/test_schemas_planning.py`
- Test: `tests/test_jobs_manager.py` (extend existing file if present, else create)
- Test: `tests/test_storage_files.py` (extend existing file)

**Interfaces:**
- Produces: `Settings.openrouter_model_planning/content/activities/assessment/gaps: str` (all default `"openai/gpt-4o-mini"`); `app.schemas.planning.{PeriodPlan, TeachingPlanSkeleton, PeriodContent, Activity, ActivitiesResponse, Assessment, GapAnalysisItem, GapAnalysisResponse, PeriodPackage, TeachingPlan}`; `JobManager.create_job(file_path, job_id=None, job_type="document", parent_job_id=None) -> str` (job_type and parent_job_id now persisted and returned by `get_job`); `save_plan_result_json(storage_dir, job_id, content) -> str`.
- Consumes: `app.schemas.extraction.{SourceRef, ConceptItem}` (existing).

- [ ] **Step 1: Write failing tests for the new schemas**

Create `tests/test_schemas_planning.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.extraction import ConceptItem, SourceRef
from app.schemas.planning import (
    Activity,
    ActivitiesResponse,
    Assessment,
    GapAnalysisItem,
    GapAnalysisResponse,
    PeriodContent,
    PeriodPackage,
    PeriodPlan,
    TeachingPlan,
    TeachingPlanSkeleton,
)


def _concept_item():
    return ConceptItem(text="Newton's First Law", source_ref=SourceRef(page=3))


def test_period_plan_roundtrip():
    plan = PeriodPlan(
        period_no=1, duration_min=40, title="Intro to Motion",
        objectives=["Explain inertia"], concepts_covered=["inertia"],
        sequencing_notes="Foundational concept, taught first.",
    )
    assert TeachingPlanSkeleton(periods=[plan]).periods[0].period_no == 1


def test_period_content_requires_grounded_notes():
    content = PeriodContent(
        entry_ticket="Quick recap question", teacher_script="Explain inertia...",
        blackboard_notes="Inertia = resistance to change in motion",
        checkpoint_questions=["What is inertia?"], exit_ticket="One thing you learned",
        homework="Read next section", mentor_moment="Story about a bus stopping suddenly",
        grounded_notes=[_concept_item()],
    )
    assert content.grounded_notes[0].source_ref.page == 3


def test_activities_response_wraps_list():
    resp = ActivitiesResponse(activities=[
        Activity(type="demonstration", duration_min=10, materials=["ball", "table"],
                  teacher_instructions="Roll the ball", success_criteria="Students predict motion")
    ])
    assert len(resp.activities) == 1


def test_assessment_roundtrip():
    assessment = Assessment(
        mcqs=["Q1..."], short_answer=["Q2..."], long_answer=["Q3..."], numerical=["Q4..."],
        answer_key="1-B, 2-...", rubric="Award 1 point per correct step",
    )
    assert assessment.mcqs == ["Q1..."]


def test_gap_analysis_response_wraps_list():
    resp = GapAnalysisResponse(gap_analysis=[
        GapAnalysisItem(
            misconception=_concept_item(), diagnostic_questions=["Does a moving object stop on its own?"],
            severity="high", remedial_action="Demonstrate with a frictionless simulation",
        )
    ])
    assert resp.gap_analysis[0].severity == "high"


def test_gap_analysis_rejects_invalid_severity_free_text_allowed():
    # severity is a plain string (not an enum) — any value is accepted by the schema;
    # this test documents that choice rather than asserting a validation error.
    item = GapAnalysisItem(
        misconception=_concept_item(), diagnostic_questions=["..."],
        severity="medium", remedial_action="...",
    )
    assert item.severity == "medium"


def test_teaching_plan_roundtrip():
    plan = PeriodPlan(
        period_no=1, duration_min=40, title="Intro", objectives=["obj"],
        concepts_covered=["c"], sequencing_notes="notes",
    )
    content = PeriodContent(
        entry_ticket="e", teacher_script="s", blackboard_notes="b",
        checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
        grounded_notes=[_concept_item()],
    )
    activity = Activity(type="demo", duration_min=5, materials=["m"],
                          teacher_instructions="i", success_criteria="s")
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"],
                              numerical=["q"], answer_key="k", rubric="r")
    package = PeriodPackage(plan=plan, content=content, activities=[activity], assessment=assessment)
    gap = GapAnalysisItem(misconception=_concept_item(), diagnostic_questions=["q"],
                            severity="low", remedial_action="a")
    tp = TeachingPlan(job_id="job-1", source_job_id="job-0", periods=[package], gap_analysis=[gap])
    assert tp.periods[0].plan.title == "Intro"
    assert tp.model_dump_json()  # serializes without error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schemas_planning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.planning'`

- [ ] **Step 3: Add new OpenRouter model settings**

Modify `app/config.py` — add these four fields to `Settings`, directly below `openrouter_model_extraction`:

```python
    openrouter_model_planning: str = "openai/gpt-4o-mini"
    openrouter_model_content: str = "openai/gpt-4o-mini"
    openrouter_model_activities: str = "openai/gpt-4o-mini"
    openrouter_model_assessment: str = "openai/gpt-4o-mini"
    openrouter_model_gaps: str = "openai/gpt-4o-mini"
```

- [ ] **Step 4: Create the planning schemas module**

Create `app/schemas/planning.py`:

```python
from pydantic import BaseModel

from app.schemas.extraction import ConceptItem


class PeriodPlan(BaseModel):
    period_no: int
    duration_min: int
    title: str
    objectives: list[str]
    concepts_covered: list[str]
    sequencing_notes: str


class TeachingPlanSkeleton(BaseModel):
    periods: list[PeriodPlan]


class PeriodContent(BaseModel):
    entry_ticket: str
    teacher_script: str
    blackboard_notes: str
    checkpoint_questions: list[str]
    exit_ticket: str
    homework: str
    mentor_moment: str
    grounded_notes: list[ConceptItem]


class Activity(BaseModel):
    type: str
    duration_min: int
    materials: list[str]
    teacher_instructions: str
    success_criteria: str


class ActivitiesResponse(BaseModel):
    activities: list[Activity]


class Assessment(BaseModel):
    mcqs: list[str]
    short_answer: list[str]
    long_answer: list[str]
    numerical: list[str]
    answer_key: str
    rubric: str


class GapAnalysisItem(BaseModel):
    misconception: ConceptItem
    diagnostic_questions: list[str]
    severity: str
    remedial_action: str


class GapAnalysisResponse(BaseModel):
    gap_analysis: list[GapAnalysisItem]


class PeriodPackage(BaseModel):
    plan: PeriodPlan
    content: PeriodContent
    activities: list[Activity]
    assessment: Assessment


class TeachingPlan(BaseModel):
    job_id: str
    source_job_id: str
    periods: list[PeriodPackage]
    gap_analysis: list[GapAnalysisItem]
```

- [ ] **Step 5: Run schema tests to verify they pass**

Run: `uv run pytest tests/test_schemas_planning.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Write failing tests for JobManager's job_type/parent_job_id**

Add to `tests/test_jobs_manager.py` (create the file with this content if it does not already exist; if it exists, append these two test functions and add the `import` lines if missing):

```python
from app.jobs.manager import JobManager


def test_create_job_defaults_job_type_document(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path="/tmp/x.pdf")
    job = manager.get_job(job_id)
    assert job["job_type"] == "document"
    assert job["parent_job_id"] is None


def test_create_job_accepts_plan_type_and_parent(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    parent_id = manager.create_job(file_path="/tmp/x.pdf")
    plan_id = manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=parent_id)
    job = manager.get_job(plan_id)
    assert job["job_type"] == "plan"
    assert job["parent_job_id"] == parent_id
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_jobs_manager.py -v`
Expected: FAIL — `KeyError: 'job_type'` (column does not exist yet)

- [ ] **Step 8: Add job_type and parent_job_id to JobManager**

Modify `app/jobs/manager.py` — replace the `SCHEMA` constant and `create_job` method:

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    stage TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    file_path TEXT NOT NULL,
    result_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    job_type TEXT NOT NULL DEFAULT 'document',
    parent_job_id TEXT
);
"""
```

```python
    def create_job(
        self,
        file_path: str,
        job_id: Optional[str] = None,
        job_type: str = "document",
        parent_job_id: Optional[str] = None,
    ) -> str:
        job_id = job_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, stage, progress, file_path, result_path, "
                "error, created_at, updated_at, job_type, parent_job_id) "
                "VALUES (?, 'queued', NULL, 0, ?, NULL, NULL, ?, ?, ?, ?)",
                (job_id, file_path, now, now, job_type, parent_job_id),
            )
        return job_id
```

Leave `update_job` and `get_job` unchanged — `get_job` already does `SELECT * FROM jobs`, so the new columns come through automatically.

- [ ] **Step 9: Run tests to verify they pass**

Run: `uv run pytest tests/test_jobs_manager.py -v`
Expected: PASS (2 new tests; if the file pre-existed with other tests, all pass)

- [ ] **Step 10: Write failing test for save_plan_result_json**

Add to `tests/test_storage_files.py`:

```python
from app.storage.files import save_plan_result_json


def test_save_plan_result_json_writes_teaching_plan_file(tmp_path):
    path = save_plan_result_json(str(tmp_path), "job-1", '{"job_id": "job-1"}')
    assert Path(path).name == "TeachingPlan.json"
    assert Path(path).read_text() == '{"job_id": "job-1"}'
```

(If `tests/test_storage_files.py` does not already import `Path` from `pathlib`, add `from pathlib import Path` at the top.)

- [ ] **Step 11: Run test to verify it fails**

Run: `uv run pytest tests/test_storage_files.py -v`
Expected: FAIL with `ImportError: cannot import name 'save_plan_result_json'`

- [ ] **Step 12: Add save_plan_result_json**

Modify `app/storage/files.py` — add this function after `save_result_json`:

```python
def save_plan_result_json(storage_dir: str, job_id: str, content: str) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "TeachingPlan.json"
    dest_path.write_text(content, encoding="utf-8")
    return str(dest_path)
```

- [ ] **Step 13: Run full test suite**

Run: `uv run pytest -v`
Expected: all pass (Phase 1's 34 plus this task's new tests)

- [ ] **Step 14: Commit**

```bash
git add app/config.py app/schemas/planning.py app/jobs/manager.py app/storage/files.py tests/test_schemas_planning.py tests/test_jobs_manager.py tests/test_storage_files.py
git commit -m "feat: add Phase 2 schemas, job_type/parent_job_id tracking, plan result storage"
```

---

### Task 2: Stage 4 — Teaching Planner

**Files:**
- Create: `app/planning/__init__.py` (empty)
- Create: `app/planning/prompts.py`
- Create: `app/planning/plan.py`
- Test: `tests/test_planning.py`

**Interfaces:**
- Consumes: `app.schemas.extraction.KnowledgeExtract`, `app.schemas.classification.ClassificationResult`, `app.llm.openrouter_client.{OpenRouterClient, LLMResponseError}`, `app.config.settings.openrouter_model_planning`, `app.schemas.planning.TeachingPlanSkeleton`.
- Produces: `plan_periods(knowledge: KnowledgeExtract, classification: ClassificationResult, client: Optional[OpenRouterClient] = None) -> TeachingPlanSkeleton`.

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_planning.py`:

```python
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.llm.openrouter_client import LLMResponseError
from app.planning.plan import plan_periods
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    return KnowledgeExtract(
        learning_objectives=[item], prerequisites=[item], concepts=[item],
        definitions=[item], formulae=[item], keywords=[item], examples=[item],
        applications=[item], misconceptions=[item],
    )


def _classification():
    return ClassificationResult(
        subject="Physics", grade="9", difficulty="medium", topic="Motion",
        chapter="Laws of Motion", category="STEM", language="English",
    )


def test_plan_periods_returns_valid_skeleton():
    client = MagicMock()
    client.complete_json.return_value = {
        "periods": [
            {"period_no": 1, "duration_min": 40, "title": "Intro to Inertia",
             "objectives": ["Explain inertia"], "concepts_covered": ["Inertia"],
             "sequencing_notes": "First concept taught."}
        ]
    }
    result = plan_periods(_knowledge(), _classification(), client=client)
    assert result.periods[0].title == "Intro to Inertia"
    client.complete_json.assert_called_once()


def test_plan_periods_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [
        LLMResponseError("bad json"),
        {"periods": [{"period_no": 1, "duration_min": 40, "title": "Intro",
                       "objectives": ["obj"], "concepts_covered": ["c"],
                       "sequencing_notes": "notes"}]},
    ]
    result = plan_periods(_knowledge(), _classification(), client=client)
    assert len(result.periods) == 1
    assert client.complete_json.call_count == 2


def test_plan_periods_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        plan_periods(_knowledge(), _classification(), client=client)
    assert client.complete_json.call_count == 3  # MAX_RETRIES=2 + initial attempt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_planning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.planning'`

- [ ] **Step 3: Create the package init**

Create `app/planning/__init__.py` (empty file).

- [ ] **Step 4: Create the prompts module**

Create `app/planning/prompts.py`:

```python
SYSTEM_PROMPT = """You are an expert curriculum planner. Given a chapter's structured knowledge
extract (learning objectives, prerequisites, concepts, definitions, formulae, examples) and its
classification (grade/subject/difficulty), design a multi-period teaching plan. Decide the number
of periods and each period's duration based on content volume, conceptual complexity, and the
target grade level — do not assume a fixed number of periods or a fixed duration such as "5
periods of 40 minutes" unless the content genuinely calls for it. Every period must have a title,
one or more objectives, the concepts it covers (drawn only from the provided concepts/definitions,
not invented), and sequencing_notes explaining why it comes at that point in the chapter. You may
use general pedagogy knowledge to decide sequencing and pacing, but every concept named must come
from the provided knowledge extract — do not introduce subject matter absent from it. Respond ONLY
with a JSON object with exactly one key "periods", an array of objects each with: period_no (int),
duration_min (int), title (string), objectives (array of strings), concepts_covered (array of
strings), sequencing_notes (string)."""

MAX_CONTEXT_CHARS = 8000


def build_user_prompt(knowledge: dict, classification: dict) -> str:
    return (
        f"Classification: {classification}\n\n"
        f"Knowledge extract:\n{str(knowledge)[:MAX_CONTEXT_CHARS]}"
    )
```

- [ ] **Step 5: Create the plan module**

Create `app/planning/plan.py`:

```python
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
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid JSON or missing required "
            "keys. Return ONLY a valid JSON object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_planning, SYSTEM_PROMPT, prompt)
            return TeachingPlanSkeleton.model_validate(raw)
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_planning.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add app/planning tests/test_planning.py
git commit -m "feat: add Stage 4 teaching planner"
```

---

### Task 3: Stage 5 — Classroom Content Generation

**Files:**
- Create: `app/content/__init__.py` (empty)
- Create: `app/content/prompts.py`
- Create: `app/content/generate.py`
- Test: `tests/test_content.py`

**Interfaces:**
- Consumes: `app.schemas.planning.{PeriodPlan, PeriodContent}`, `app.schemas.extraction.KnowledgeExtract`, `app.schemas.classification.ClassificationResult`, `app.llm.openrouter_client.{OpenRouterClient, LLMResponseError}`, `app.config.settings.openrouter_model_content`.
- Produces: `generate_content(period: PeriodPlan, knowledge: KnowledgeExtract, classification: ClassificationResult, client: Optional[OpenRouterClient] = None) -> PeriodContent`.

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_content.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.content.generate import generate_content
from app.llm.openrouter_client import LLMResponseError
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import PeriodPlan


def _period():
    return PeriodPlan(period_no=1, duration_min=40, title="Intro to Inertia",
                        objectives=["Explain inertia"], concepts_covered=["Inertia"],
                        sequencing_notes="First concept.")


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    return KnowledgeExtract(
        learning_objectives=[item], prerequisites=[item], concepts=[item],
        definitions=[item], formulae=[item], keywords=[item], examples=[item],
        applications=[item], misconceptions=[item],
    )


def _classification():
    return ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                  topic="Motion", chapter="Laws of Motion",
                                  category="STEM", language="English")


def _valid_response():
    return {
        "entry_ticket": "What keeps a ball rolling?", "teacher_script": "Today we discuss inertia...",
        "blackboard_notes": "Inertia: resistance to change in motion",
        "checkpoint_questions": ["What is inertia?"], "exit_ticket": "Name one example of inertia",
        "homework": "Find 3 examples of inertia at home", "mentor_moment": "Bus stopping suddenly story",
        "grounded_notes": [{"text": "Inertia", "source_ref": {"page": 1, "section": None}}],
    }


def test_generate_content_returns_valid_period_content():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    result = generate_content(_period(), _knowledge(), _classification(), client=client)
    assert result.entry_ticket == "What keeps a ball rolling?"
    assert result.grounded_notes[0].source_ref.page == 1


def test_generate_content_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    result = generate_content(_period(), _knowledge(), _classification(), client=client)
    assert result.teacher_script.startswith("Today we discuss")
    assert client.complete_json.call_count == 2


def test_generate_content_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        generate_content(_period(), _knowledge(), _classification(), client=client)
    assert client.complete_json.call_count == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_content.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.content'`

- [ ] **Step 3: Create the package init**

Create `app/content/__init__.py` (empty file).

- [ ] **Step 4: Create the prompts module**

Create `app/content/prompts.py`:

```python
SYSTEM_PROMPT = """You are an expert classroom teacher preparing detailed material for a single
lesson period. Given the period's plan (title, objectives, concepts to cover) and the chapter's
full knowledge extract for grounding, produce complete classroom-ready content: an entry ticket
(warm-up question), a teacher script (what the teacher says/does, narrative form), blackboard
notes (what gets written on the board), checkpoint questions (asked mid-lesson to check
understanding), an exit ticket, homework, and a "mentor moment" (a short motivational anecdote or
real-world story tied to the topic). You may draw on general teaching strategies, analogies, and
stories to make the content engaging, but every factual/conceptual claim about the subject matter
must come from the provided knowledge extract — do not introduce new facts, data, or concepts
beyond it. List every concept-bearing claim you used from the knowledge extract in
"grounded_notes" as objects with "text" and "source_ref" (page/section), copying the source_ref
from the matching item in the knowledge extract. Respond ONLY with a JSON object with exactly these
keys: entry_ticket, teacher_script, blackboard_notes, checkpoint_questions (array of strings),
exit_ticket, homework, mentor_moment, grounded_notes (array of objects with "text" and
"source_ref")."""

MAX_CONTEXT_CHARS = 8000


def build_user_prompt(period: dict, knowledge: dict, classification: dict) -> str:
    return (
        f"Classification: {classification}\n\n"
        f"Period plan: {period}\n\n"
        f"Knowledge extract:\n{str(knowledge)[:MAX_CONTEXT_CHARS]}"
    )
```

- [ ] **Step 5: Create the generate module**

Create `app/content/generate.py`:

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_content.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add app/content tests/test_content.py
git commit -m "feat: add Stage 5 classroom content generation"
```

---

### Task 4: Stage 6 — Activity Generation

**Files:**
- Create: `app/activities/__init__.py` (empty)
- Create: `app/activities/prompts.py`
- Create: `app/activities/generate.py`
- Test: `tests/test_activities.py`

**Interfaces:**
- Consumes: `app.schemas.planning.{PeriodPlan, PeriodContent, Activity, ActivitiesResponse}`, `app.llm.openrouter_client.{OpenRouterClient, LLMResponseError}`, `app.config.settings.openrouter_model_activities`.
- Produces: `generate_activities(period: PeriodPlan, content: PeriodContent, client: Optional[OpenRouterClient] = None) -> list[Activity]`.

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_activities.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.activities.generate import generate_activities
from app.llm.openrouter_client import LLMResponseError
from app.schemas.extraction import ConceptItem, SourceRef
from app.schemas.planning import PeriodContent, PeriodPlan


def _period():
    return PeriodPlan(period_no=1, duration_min=40, title="Intro to Inertia",
                        objectives=["Explain inertia"], concepts_covered=["Inertia"],
                        sequencing_notes="First concept.")


def _content():
    return PeriodContent(
        entry_ticket="e", teacher_script="s", blackboard_notes="b",
        checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
        grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))],
    )


def _valid_response():
    return {"activities": [
        {"type": "demonstration", "duration_min": 10, "materials": ["ball", "table"],
         "teacher_instructions": "Roll the ball across the table", "success_criteria": "Students predict it keeps moving"},
    ]}


def test_generate_activities_returns_list():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    result = generate_activities(_period(), _content(), client=client)
    assert len(result) == 1
    assert result[0].type == "demonstration"


def test_generate_activities_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    result = generate_activities(_period(), _content(), client=client)
    assert len(result) == 1
    assert client.complete_json.call_count == 2


def test_generate_activities_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        generate_activities(_period(), _content(), client=client)
    assert client.complete_json.call_count == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_activities.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.activities'`

- [ ] **Step 3: Create the package init**

Create `app/activities/__init__.py` (empty file).

- [ ] **Step 4: Create the prompts module**

Create `app/activities/prompts.py`:

```python
SYSTEM_PROMPT = """You are an expert in classroom pedagogy designing hands-on activities
(demonstrations, role play, experiments, group work, etc.) for a single lesson period. Given the
period's plan and its already-generated classroom content, design one or more diverse activities
appropriate for the grade level and duration of the period. Each activity needs a type, a duration
in minutes, a list of materials needed, step-by-step teacher instructions, and clear success
criteria describing what indicates the activity worked. You may use general pedagogy and classroom
management knowledge to design the activity mechanics, but the subject matter the activity
teaches must stay grounded in the period's content — do not introduce facts beyond it. Respond
ONLY with a JSON object with exactly one key "activities", an array of objects each with: type
(string), duration_min (int), materials (array of strings), teacher_instructions (string),
success_criteria (string)."""

MAX_CONTEXT_CHARS = 8000


def build_user_prompt(period: dict, content: dict) -> str:
    return (
        f"Period plan: {period}\n\n"
        f"Period content:\n{str(content)[:MAX_CONTEXT_CHARS]}"
    )
```

- [ ] **Step 5: Create the generate module**

Create `app/activities/generate.py`:

```python
from typing import Optional

from pydantic import ValidationError

from app.activities.prompts import SYSTEM_PROMPT, build_user_prompt
from app.config import settings
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.planning import Activity, ActivitiesResponse, PeriodContent, PeriodPlan

MAX_RETRIES = 2


def generate_activities(
    period: PeriodPlan,
    content: PeriodContent,
    client: Optional[OpenRouterClient] = None,
) -> list[Activity]:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(period.model_dump(), content.model_dump())

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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_activities.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add app/activities tests/test_activities.py
git commit -m "feat: add Stage 6 activity generation"
```

---

### Task 5: Stage 7 — Assessment Generation

**Files:**
- Create: `app/assessment/__init__.py` (empty)
- Create: `app/assessment/prompts.py`
- Create: `app/assessment/generate.py`
- Test: `tests/test_assessment.py`

**Interfaces:**
- Consumes: `app.schemas.planning.{PeriodPlan, PeriodContent, Assessment}`, `app.llm.openrouter_client.{OpenRouterClient, LLMResponseError}`, `app.config.settings.openrouter_model_assessment`.
- Produces: `generate_assessment(period: PeriodPlan, content: PeriodContent, client: Optional[OpenRouterClient] = None) -> Assessment`.

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_assessment.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.assessment.generate import generate_assessment
from app.llm.openrouter_client import LLMResponseError
from app.schemas.extraction import ConceptItem, SourceRef
from app.schemas.planning import PeriodContent, PeriodPlan


def _period():
    return PeriodPlan(period_no=1, duration_min=40, title="Intro to Inertia",
                        objectives=["Explain inertia"], concepts_covered=["Inertia"],
                        sequencing_notes="First concept.")


def _content():
    return PeriodContent(
        entry_ticket="e", teacher_script="s", blackboard_notes="b",
        checkpoint_questions=["q"], exit_ticket="x", homework="h", mentor_moment="m",
        grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))],
    )


def _valid_response():
    return {
        "mcqs": ["Which of these demonstrates inertia? A) ... B) ..."],
        "short_answer": ["Define inertia in your own words."],
        "long_answer": ["Explain how inertia applies to seatbelt safety."],
        "numerical": ["A 2kg object..."],
        "answer_key": "MCQ1: B",
        "rubric": "1 point per correct concept referenced",
    }


def test_generate_assessment_returns_valid_assessment():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    result = generate_assessment(_period(), _content(), client=client)
    assert result.answer_key == "MCQ1: B"


def test_generate_assessment_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    result = generate_assessment(_period(), _content(), client=client)
    assert result.rubric.startswith("1 point")
    assert client.complete_json.call_count == 2


def test_generate_assessment_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        generate_assessment(_period(), _content(), client=client)
    assert client.complete_json.call_count == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_assessment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.assessment'`

- [ ] **Step 3: Create the package init**

Create `app/assessment/__init__.py` (empty file).

- [ ] **Step 4: Create the prompts module**

Create `app/assessment/prompts.py`:

```python
SYSTEM_PROMPT = """You are an expert assessment designer creating a comprehensive assessment for a
single lesson period. Given the period's plan and its classroom content, generate a mix of
question types: multiple choice questions (with options embedded in the question text), short
answer questions, long answer questions, and numerical/problem-solving questions where the subject
allows it (leave numerical as an empty array if the subject has no numerical component, e.g. a
purely narrative humanities topic). Also produce a combined answer key and a grading rubric. Every
question must test material grounded in the period's content — do not introduce facts beyond it.
Respond ONLY with a JSON object with exactly these keys: mcqs (array of strings), short_answer
(array of strings), long_answer (array of strings), numerical (array of strings, may be empty),
answer_key (string), rubric (string)."""

MAX_CONTEXT_CHARS = 8000


def build_user_prompt(period: dict, content: dict) -> str:
    return (
        f"Period plan: {period}\n\n"
        f"Period content:\n{str(content)[:MAX_CONTEXT_CHARS]}"
    )
```

- [ ] **Step 5: Create the generate module**

Create `app/assessment/generate.py`:

```python
from typing import Optional

from pydantic import ValidationError

from app.assessment.prompts import SYSTEM_PROMPT, build_user_prompt
from app.config import settings
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.planning import Assessment, PeriodContent, PeriodPlan

MAX_RETRIES = 2


def generate_assessment(
    period: PeriodPlan,
    content: PeriodContent,
    client: Optional[OpenRouterClient] = None,
) -> Assessment:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(period.model_dump(), content.model_dump())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid JSON or missing required "
            "keys. Return ONLY a valid JSON object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_assessment, SYSTEM_PROMPT, prompt)
            return Assessment.model_validate(raw)
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_assessment.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add app/assessment tests/test_assessment.py
git commit -m "feat: add Stage 7 assessment generation"
```

---

### Task 6: Stage 8 — Learning Gap Analysis

**Files:**
- Create: `app/gaps/__init__.py` (empty)
- Create: `app/gaps/prompts.py`
- Create: `app/gaps/generate.py`
- Test: `tests/test_gaps.py`

**Interfaces:**
- Consumes: `app.schemas.extraction.KnowledgeExtract`, `app.schemas.planning.{PeriodPackage, GapAnalysisItem, GapAnalysisResponse}`, `app.llm.openrouter_client.{OpenRouterClient, LLMResponseError}`, `app.config.settings.openrouter_model_gaps`.
- Produces: `generate_gaps(knowledge: KnowledgeExtract, periods: list[PeriodPackage], client: Optional[OpenRouterClient] = None) -> list[GapAnalysisItem]`.

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_gaps.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.gaps.generate import generate_gaps
from app.llm.openrouter_client import LLMResponseError
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.planning import Assessment, PeriodContent, PeriodPackage, PeriodPlan


def _knowledge():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    misconception = ConceptItem(text="Objects need a constant push to keep moving", source_ref=SourceRef(page=2))
    return KnowledgeExtract(
        learning_objectives=[item], prerequisites=[item], concepts=[item],
        definitions=[item], formulae=[item], keywords=[item], examples=[item],
        applications=[item], misconceptions=[misconception],
    )


def _period_package():
    plan = PeriodPlan(period_no=1, duration_min=40, title="Intro", objectives=["obj"],
                        concepts_covered=["c"], sequencing_notes="notes")
    content = PeriodContent(entry_ticket="e", teacher_script="s", blackboard_notes="b",
                              checkpoint_questions=["What is inertia?"], exit_ticket="x",
                              homework="h", mentor_moment="m",
                              grounded_notes=[ConceptItem(text="Inertia", source_ref=SourceRef(page=1))])
    assessment = Assessment(mcqs=["q"], short_answer=["q"], long_answer=["q"], numerical=["q"],
                              answer_key="k", rubric="r")
    return PeriodPackage(plan=plan, content=content, activities=[], assessment=assessment)


def _valid_response():
    return {"gap_analysis": [
        {"misconception": {"text": "Objects need a constant push to keep moving",
                             "source_ref": {"page": 2, "section": None}},
         "diagnostic_questions": ["Does a hockey puck slow down due to lack of force or due to friction?"],
         "severity": "high", "remedial_action": "Demonstrate motion on a low-friction surface"}
    ]}


def test_generate_gaps_returns_list():
    client = MagicMock()
    client.complete_json.return_value = _valid_response()
    result = generate_gaps(_knowledge(), [_period_package()], client=client)
    assert len(result) == 1
    assert result[0].severity == "high"


def test_generate_gaps_retries_on_invalid_json_then_succeeds():
    client = MagicMock()
    client.complete_json.side_effect = [LLMResponseError("bad"), _valid_response()]
    result = generate_gaps(_knowledge(), [_period_package()], client=client)
    assert len(result) == 1
    assert client.complete_json.call_count == 2


def test_generate_gaps_raises_after_exhausting_retries():
    client = MagicMock()
    client.complete_json.side_effect = LLMResponseError("always bad")
    with pytest.raises(LLMResponseError):
        generate_gaps(_knowledge(), [_period_package()], client=client)
    assert client.complete_json.call_count == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gaps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.gaps'`

- [ ] **Step 3: Create the package init**

Create `app/gaps/__init__.py` (empty file).

- [ ] **Step 4: Create the prompts module**

Create `app/gaps/prompts.py`:

```python
SYSTEM_PROMPT = """You are an expert in diagnosing student learning gaps. Given the chapter's full
knowledge extract (specifically its "misconceptions" list) and the checkpoint/assessment questions
already generated across all periods of the teaching plan, produce a learning gap analysis: for
each misconception, provide one or more diagnostic questions a teacher could ask to detect whether
a student holds that misconception, a severity level ("low", "medium", or "high") reflecting how
much it would impede understanding of the chapter, and a concrete remedial action the teacher can
take. Ground every misconception in the provided list — do not invent misconceptions absent from
it. You may use general learning-science knowledge to design the diagnostic questions and remedial
actions. Respond ONLY with a JSON object with exactly one key "gap_analysis", an array of objects
each with: misconception (an object with "text" and "source_ref", copied from the input
misconceptions list), diagnostic_questions (array of strings), severity (string: low/medium/high),
remedial_action (string)."""

MAX_CONTEXT_CHARS = 8000


def build_user_prompt(knowledge: dict, periods: list[dict]) -> str:
    checkpoint_questions = [
        q for p in periods
        for q in (p.get("content", {}).get("checkpoint_questions", []) + p.get("assessment", {}).get("mcqs", []))
    ]
    return (
        f"Misconceptions:\n{knowledge.get('misconceptions')}\n\n"
        f"Checkpoint/assessment questions already asked across periods:\n{checkpoint_questions}\n\n"
        f"Full knowledge extract (for context):\n{str(knowledge)[:MAX_CONTEXT_CHARS]}"
    )
```

- [ ] **Step 5: Create the generate module**

Create `app/gaps/generate.py`:

```python
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
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid JSON or missing required "
            "keys. Return ONLY a valid JSON object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_gaps, SYSTEM_PROMPT, prompt)
            return GapAnalysisResponse.model_validate(raw).gap_analysis
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_gaps.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add app/gaps tests/test_gaps.py
git commit -m "feat: add Stage 8 learning gap analysis"
```

---

### Task 7: Plan pipeline orchestration

**Files:**
- Create: `app/jobs/pipeline_plan.py`
- Test: `tests/test_pipeline_plan.py`

**Interfaces:**
- Consumes: `app.planning.plan.plan_periods`, `app.content.generate.generate_content`, `app.activities.generate.generate_activities`, `app.assessment.generate.generate_assessment`, `app.gaps.generate.generate_gaps`, `app.jobs.manager.JobManager`, `app.schemas.document_knowledge.DocumentKnowledgeExtract`, `app.schemas.planning.{PeriodPackage, TeachingPlan}`, `app.storage.files.save_plan_result_json`.
- Produces: `async def run_plan_pipeline(job_manager: JobManager, storage_dir: str, job_id: str, source: DocumentKnowledgeExtract, source_job_id: str) -> None`.

- [ ] **Step 1: Write failing integration test**

Create `tests/test_pipeline_plan.py`:

```python
from unittest.mock import patch

import pytest

from app.jobs.manager import JobManager
from app.jobs.pipeline_plan import run_plan_pipeline
from app.schemas.classification import ClassificationResult
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section


def _source():
    item = ConceptItem(text="Inertia", source_ref=SourceRef(page=1))
    knowledge = KnowledgeExtract(
        learning_objectives=[item], prerequisites=[item], concepts=[item],
        definitions=[item], formulae=[item], keywords=[item], examples=[item],
        applications=[item], misconceptions=[item],
    )
    classification = ClassificationResult(subject="Physics", grade="9", difficulty="medium",
                                            topic="Motion", chapter="Laws of Motion",
                                            category="STEM", language="English")
    parsed = ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[Section(heading="Intro", text="Body.", page=1)],
    )
    return DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)


PERIOD_SKELETON = {"periods": [
    {"period_no": 1, "duration_min": 40, "title": "Intro to Inertia", "objectives": ["Explain inertia"],
     "concepts_covered": ["Inertia"], "sequencing_notes": "First concept."},
    {"period_no": 2, "duration_min": 40, "title": "Applying Inertia", "objectives": ["Apply inertia"],
     "concepts_covered": ["Inertia"], "sequencing_notes": "Builds on period 1."},
]}

CONTENT_RESPONSE = {
    "entry_ticket": "e", "teacher_script": "s", "blackboard_notes": "b",
    "checkpoint_questions": ["q"], "exit_ticket": "x", "homework": "h", "mentor_moment": "m",
    "grounded_notes": [{"text": "Inertia", "source_ref": {"page": 1, "section": None}}],
}
ACTIVITIES_RESPONSE = {"activities": [
    {"type": "demo", "duration_min": 10, "materials": ["ball"], "teacher_instructions": "roll it", "success_criteria": "predicts motion"}
]}
ASSESSMENT_RESPONSE = {"mcqs": ["q"], "short_answer": ["q"], "long_answer": ["q"], "numerical": ["q"], "answer_key": "k", "rubric": "r"}
GAPS_RESPONSE = {"gap_analysis": [
    {"misconception": {"text": "Inertia", "source_ref": {"page": 1, "section": None}},
     "diagnostic_questions": ["q"], "severity": "low", "remedial_action": "a"}
]}


@pytest.mark.asyncio
async def test_run_plan_pipeline_completes_with_two_periods(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    job_manager.update_job(source_job_id, status="completed", result_path="/tmp/DocumentKnowledgeExtract.json")
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)

    with patch("app.jobs.pipeline_plan.plan_periods") as mock_plan, \
         patch("app.jobs.pipeline_plan.generate_content") as mock_content, \
         patch("app.jobs.pipeline_plan.generate_activities") as mock_activities, \
         patch("app.jobs.pipeline_plan.generate_assessment") as mock_assessment, \
         patch("app.jobs.pipeline_plan.generate_gaps") as mock_gaps:
        from app.schemas.planning import Activity, Assessment, GapAnalysisItem, PeriodContent, TeachingPlanSkeleton

        mock_plan.return_value = TeachingPlanSkeleton.model_validate(PERIOD_SKELETON)
        mock_content.return_value = PeriodContent.model_validate(CONTENT_RESPONSE)
        mock_activities.return_value = [Activity.model_validate(a) for a in ACTIVITIES_RESPONSE["activities"]]
        mock_assessment.return_value = Assessment.model_validate(ASSESSMENT_RESPONSE)
        mock_gaps.return_value = [GapAnalysisItem.model_validate(g) for g in GAPS_RESPONSE["gap_analysis"]]

        await run_plan_pipeline(job_manager, str(tmp_path), job_id, _source(), source_job_id)

    job = job_manager.get_job(job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert job["result_path"] is not None
    assert mock_content.call_count == 2
    assert mock_activities.call_count == 2
    assert mock_assessment.call_count == 2
    assert mock_gaps.call_count == 1


@pytest.mark.asyncio
async def test_run_plan_pipeline_marks_failed_on_stage_error(tmp_path):
    job_manager = JobManager(str(tmp_path / "jobs.db"))
    source_job_id = job_manager.create_job(file_path="/tmp/x.pdf")
    job_id = job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=source_job_id)

    with patch("app.jobs.pipeline_plan.plan_periods", side_effect=RuntimeError("boom")):
        await run_plan_pipeline(job_manager, str(tmp_path), job_id, _source(), source_job_id)

    job = job_manager.get_job(job_id)
    assert job["status"] == "failed"
    assert "boom" in job["error"]
```

Note: this test uses `@pytest.mark.asyncio`. Check whether `pytest-asyncio` is already a dependency (Phase 1's `test_api_documents.py` uses `AsyncMock`/`TestClient` patterns — check `pyproject.toml`). If `pytest-asyncio` is not installed, add it: `uv add --dev pytest-asyncio` and add to `pyproject.toml`'s pytest config (or a `pytest.ini`/`[tool.pytest.ini_options]` block) `asyncio_mode = "auto"` so the `@pytest.mark.asyncio` decorator (or bare `async def test_...`) runs correctly — mirror whatever async test setup Phase 1 already established; if Phase 1 tests call async pipeline code directly with `asyncio.run(...)` instead, use that same pattern here rather than introducing a new dependency.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jobs.pipeline_plan'`

- [ ] **Step 3: Create the pipeline module**

Create `app/jobs/pipeline_plan.py`:

```python
import asyncio
import logging

from app.activities.generate import generate_activities
from app.assessment.generate import generate_assessment
from app.content.generate import generate_content
from app.gaps.generate import generate_gaps
from app.jobs.manager import JobManager
from app.planning.plan import plan_periods
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.planning import PeriodPackage, TeachingPlan
from app.storage.files import save_plan_result_json

logger = logging.getLogger(__name__)


async def run_plan_pipeline(
    job_manager: JobManager,
    storage_dir: str,
    job_id: str,
    source: DocumentKnowledgeExtract,
    source_job_id: str,
) -> None:
    try:
        job_manager.update_job(job_id, status="running", stage="planning", progress=10)
        skeleton = await asyncio.to_thread(plan_periods, source.knowledge, source.classification)

        num_periods = len(skeleton.periods)
        packages: list[PeriodPackage] = []
        for index, period in enumerate(skeleton.periods):
            base_progress = 10 + int(70 * index / num_periods)
            step_progress = int(70 / num_periods / 3)

            job_manager.update_job(job_id, stage=f"content-period-{period.period_no}", progress=base_progress)
            content = await asyncio.to_thread(generate_content, period, source.knowledge, source.classification)

            job_manager.update_job(
                job_id, stage=f"activities-period-{period.period_no}", progress=base_progress + step_progress
            )
            activities = await asyncio.to_thread(generate_activities, period, content)

            job_manager.update_job(
                job_id, stage=f"assessment-period-{period.period_no}", progress=base_progress + 2 * step_progress
            )
            assessment = await asyncio.to_thread(generate_assessment, period, content)

            packages.append(PeriodPackage(plan=period, content=content, activities=activities, assessment=assessment))

        job_manager.update_job(job_id, stage="gap-analysis", progress=85)
        gap_analysis = await asyncio.to_thread(generate_gaps, source.knowledge, packages)

        job_manager.update_job(job_id, stage="packaging", progress=95)
        result = TeachingPlan(job_id=job_id, source_job_id=source_job_id, periods=packages, gap_analysis=gap_analysis)
        result_path = await asyncio.to_thread(
            save_plan_result_json, storage_dir, job_id, result.model_dump_json(indent=2)
        )

        job_manager.update_job(job_id, status="completed", stage="done", progress=100, result_path=result_path)
    except Exception as exc:
        logger.exception("Plan pipeline failed for job %s", job_id)
        job_manager.update_job(job_id, status="failed", error=str(exc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline_plan.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/jobs/pipeline_plan.py tests/test_pipeline_plan.py pyproject.toml uv.lock
git commit -m "feat: orchestrate Stage 4-8 plan pipeline"
```

---

### Task 8: API endpoints and wiring

**Files:**
- Create: `app/api/plans.py`
- Modify: `app/api/jobs.py`
- Modify: `app/main.py`
- Modify: `README.md`
- Test: `tests/test_api_plans.py`
- Test: `tests/test_api_jobs.py` (extend existing file)

**Interfaces:**
- Consumes: everything from Tasks 1-7.
- Produces: `POST /jobs/{job_id}/plan`, `GET /jobs/{job_id}/plan`, `GET /jobs/{job_id}/result`.

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api_plans.py`:

```python
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.main import app


def test_create_plan_404_for_unknown_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    client = TestClient(app)
    response = client.post("/jobs/does-not-exist/plan")
    assert response.status_code == 404


def test_create_plan_400_when_source_job_not_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")  # status defaults to "queued"

    client = TestClient(app)
    response = client.post(f"/jobs/{job_id}/plan")
    assert response.status_code == 400


def test_create_plan_starts_pipeline_for_completed_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))

    result_path = tmp_path / "DocumentKnowledgeExtract.json"
    result_path.write_text(json.dumps({
        "parsed_document": {
            "metadata": {"source_filename": "x.txt", "format": "txt", "page_count": 1},
            "sections": [{"heading": "Intro", "text": "Body.", "page": 1}],
            "tables": [], "figures": [], "equations": [],
        },
        "classification": {"subject": "Physics", "grade": "9", "difficulty": "medium",
                             "topic": "Motion", "chapter": "Laws", "category": "STEM", "language": "English"},
        "knowledge": {k: [] for k in ["learning_objectives", "prerequisites", "concepts", "definitions",
                                        "formulae", "keywords", "examples", "applications", "misconceptions"]},
    }))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(job_id, status="completed", result_path=str(result_path))

    with patch("app.api.plans.run_plan_pipeline", new=AsyncMock()):
        client = TestClient(app)
        response = client.post(f"/jobs/{job_id}/plan")

    assert response.status_code == 200
    plan_job_id = response.json()["id"]
    plan_job = deps.job_manager.get_job(plan_job_id)
    assert plan_job["job_type"] == "plan"
    assert plan_job["parent_job_id"] == job_id


def test_get_plan_400_when_job_is_not_a_plan_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}/plan")
    assert response.status_code == 400


def test_get_plan_returns_teaching_plan_json_when_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    result_path = tmp_path / "TeachingPlan.json"
    result_path.write_text(json.dumps({"job_id": "j1", "source_job_id": "j0", "periods": [], "gap_analysis": []}))
    parent_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    plan_job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=parent_id)
    deps.job_manager.update_job(plan_job_id, status="completed", result_path=str(result_path))

    client = TestClient(app)
    response = client.get(f"/jobs/{plan_job_id}/plan")
    assert response.status_code == 200
    assert response.json()["job_id"] == "j1"
```

Add to `tests/test_api_jobs.py` (create if it does not already exist, mirroring the imports used in `tests/test_api_plans.py` above):

```python
def test_get_job_result_returns_saved_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    result_path = tmp_path / "DocumentKnowledgeExtract.json"
    result_path.write_text('{"hello": "world"}')
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")
    deps.job_manager.update_job(job_id, status="completed", result_path=str(result_path))

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}/result")
    assert response.status_code == 200
    assert response.json() == {"hello": "world"}


def test_get_job_result_400_when_not_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.pdf")

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}/result")
    assert response.status_code == 400
```

If `tests/test_api_jobs.py` does not exist yet, create it with these imports at the top:

```python
from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.main import app
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_plans.py tests/test_api_jobs.py -v`
Expected: FAIL — `404 Not Found` for the `/plan` routes (they don't exist yet), `ModuleNotFoundError` or `AttributeError` for `run_plan_pipeline` patch target.

- [ ] **Step 3: Create the plans API module**

Create `app/api/plans.py`:

```python
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app import deps
from app.config import settings
from app.jobs.pipeline_plan import run_plan_pipeline
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.job import JobStatusResponse

router = APIRouter()

_background_tasks: set[asyncio.Task] = set()


def _to_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        id=job["id"], status=job["status"], stage=job["stage"],
        progress=job["progress"], error=job["error"], result_path=job["result_path"],
    )


@router.post("/jobs/{job_id}/plan", response_model=JobStatusResponse)
async def create_plan(job_id: str) -> JobStatusResponse:
    source_job = deps.job_manager.get_job(job_id)
    if source_job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if source_job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Source job is not completed")

    raw = await asyncio.to_thread(Path(source_job["result_path"]).read_text)
    source = DocumentKnowledgeExtract.model_validate(json.loads(raw))

    plan_job_id = deps.job_manager.create_job(
        file_path=source_job["file_path"], job_type="plan", parent_job_id=job_id
    )
    task = asyncio.create_task(
        run_plan_pipeline(deps.job_manager, settings.storage_dir, plan_job_id, source, job_id)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return _to_response(deps.job_manager.get_job(plan_job_id))


@router.get("/jobs/{job_id}/plan")
async def get_plan(job_id: str):
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["job_type"] != "plan":
        raise HTTPException(status_code=400, detail="Job is not a plan job")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Plan job is not completed")
    raw = await asyncio.to_thread(Path(job["result_path"]).read_text)
    return json.loads(raw)
```

- [ ] **Step 4: Add the generic result endpoint to the jobs API**

Modify `app/api/jobs.py` — add these imports at the top (merge with existing `asyncio`/`json` imports):

```python
from pathlib import Path
```

Add this route after `get_job`:

```python
@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed" or not job["result_path"]:
        raise HTTPException(status_code=400, detail="Job result not available")
    raw = await asyncio.to_thread(Path(job["result_path"]).read_text)
    return json.loads(raw)
```

- [ ] **Step 5: Wire the plans router into the app**

Modify `app/main.py`:

```python
from fastapi import FastAPI

from app.api import documents, jobs, plans

app = FastAPI(title="Teacher AI Platform")
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(plans.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_plans.py tests/test_api_jobs.py -v`
Expected: PASS (all tests)

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -v`
Expected: all pass (Phase 1 + all Phase 2 tests)

- [ ] **Step 8: Update README**

Modify `README.md` — add a "Phase 2: Pedagogical Planning & Generation" section after the existing Phase 1 usage documentation, describing:
- `POST /jobs/{id}/plan` (id = a completed Phase 1 document job) → starts Stage 4-8 pipeline, returns the new plan job's status.
- `GET /jobs/{id}/plan` → returns `TeachingPlan.json` once the plan job completes.
- `GET /jobs/{id}/result` → generic result fetch, works for both document jobs and plan jobs.
- A one-paragraph note that Stage 4 decides period count/duration dynamically (FAQ #3), and that every stage's prompt is grounded in the Phase 1 `KnowledgeExtract` per FAQ #4.

- [ ] **Step 9: Commit**

```bash
git add app/api/plans.py app/api/jobs.py app/main.py README.md tests/test_api_plans.py tests/test_api_jobs.py
git commit -m "feat: add Phase 2 plan API endpoints and generic job result endpoint"
```
