# Phase 2: Pedagogical Planning & Generation — Design

Date: 2026-08-04
Status: Approved

## Objective

Consume Phase 1's `DocumentKnowledgeExtract.json` and produce a
`TeachingPlan.json` covering Stages 4-8 of the assignment: multi-period
teaching plan, per-period classroom content, activities, assessments, and
a whole-chapter learning gap analysis.

Out of scope for Phase 2: Stage 9 (validation engine), Stage 10
(publishing/TKP assembly/PDF export), frontend UI. Those are Phase 3.

## Requirements traceability

| Assignment stage | Covered by |
|---|---|
| Stage 4: Teaching Planner | `planning/` |
| Stage 5: Classroom Content Generation | `content/` |
| Stage 6: Activity Generation | `activities/` |
| Stage 7: Assessment Generation | `assessment/` |
| Stage 8: Learning Gap Analysis | `gaps/` |
| Streaming Progress API | reuses Phase 1 `jobs/` + SSE endpoint |

FAQ constraints honored:
- Flexible period count/duration (FAQ #3): the planner LLM call decides
  number of periods and duration from content volume/complexity/objectives,
  not a fixed "5x40min" template.
- Grounding (FAQ #4): every stage's prompt receives the full
  `KnowledgeExtract` (objectives/concepts/definitions/misconceptions with
  their `source_ref`s) as required context. System prompts explicitly state
  outside knowledge may only shape pedagogy (analogies, activity ideas,
  teaching strategy), never introduce new subject matter. Every generated
  item that states a fact carries a `source_ref` back to the Phase 1
  extract, same pattern as Phase 1's `ConceptItem`.
- Adaptive depth (FAQ #1): no hardcoded per-subject templates; classification
  metadata (grade/subject/difficulty) flows into every stage's prompt.

## Architecture

```
Client
  │  POST /jobs/{id}/plan   (id = a completed Phase 1 job)
  ▼
FastAPI endpoint
  │  loads Phase 1 result JSON via job.result_path
  │  creates new Job row (job_type="plan"), schedules background task
  ▼
Background pipeline task
  │
  ├─ Stage 4: Teaching Planner (OpenRouter LLM call)
  │     KnowledgeExtract + ClassificationResult → TeachingPlanSkeleton
  │     {periods: [{period_no, duration_min, title, objectives[],
  │       concepts_covered[], sequencing_notes}]}
  │     Pydantic validation; retry with schema-repair prompt on failure.
  │
  ├─ For each period (sequential, not parallel):
  │     ├─ Stage 5: Classroom Content Generation (LLM call)
  │     │     period + KnowledgeExtract → PeriodContent
  │     │     {entry_ticket, teacher_script, blackboard_notes,
  │     │      checkpoint_questions[], exit_ticket, homework, mentor_moment}
  │     ├─ Stage 6: Activity Generation (LLM call)
  │     │     period + PeriodContent → list[Activity]
  │     │     {type, duration_min, materials[], teacher_instructions,
  │     │      success_criteria}
  │     └─ Stage 7: Assessment Generation (LLM call)
  │           period + PeriodContent → Assessment
  │           {mcqs[], short_answer[], long_answer[], numerical[],
  │            answer_key, rubric}
  │
  ├─ Stage 8: Learning Gap Analysis (LLM call, once, whole-chapter)
  │     KnowledgeExtract.misconceptions + all periods' checkpoint/assessment
  │     questions → list[GapAnalysisItem]
  │     {misconception, diagnostic_questions[], severity, remedial_action}
  │
  └─ Persist TeachingPlan.json (skeleton + per-period content/activities/
        assessment + gap_analysis) to filesystem; update Job status =
        completed (or failed + reason)

Client polls GET /jobs/{id} or streams GET /jobs/{id}/stream (SSE, reused
  from Phase 1) → {"stage": "...", "progress": <0-100>}
Client fetches result: GET /jobs/{id}/plan (Phase 2 job) or the generic
  GET /jobs/{id}/result (works for both Phase 1 and Phase 2 jobs).
```

## Components

- **`planning/`** — Stage 4 prompt template + `TeachingPlanSkeleton` /
  `PeriodPlan` Pydantic schemas + OpenRouter call wrapper with
  retry-on-invalid-JSON (mirrors `classification/`).
- **`content/`** — Stage 5 prompt template + `PeriodContent` schema +
  OpenRouter call wrapper, invoked once per period.
- **`activities/`** — Stage 6 prompt template + `Activity` schema +
  OpenRouter call wrapper, invoked once per period.
- **`assessment/`** — Stage 7 prompt template + `Assessment` schema +
  OpenRouter call wrapper, invoked once per period.
- **`gaps/`** — Stage 8 prompt template + `GapAnalysisItem` schema +
  OpenRouter call wrapper, invoked once per job.
- **`jobs/pipeline_plan.py`** — orchestrates stages 4-8 in sequence,
  updates job progress/stage at each step, assembles and saves
  `TeachingPlan.json`. Reuses the existing `JobManager` (add `job_type`
  column) and existing SSE endpoint unmodified.
- **`api/plans.py`** — `POST /jobs/{id}/plan`, `GET /jobs/{id}/plan`.
- **`api/jobs.py`** — add `GET /jobs/{id}/result` (generic, works for any
  completed job's `result_path`).

## Data model (high level)

- `Job` (extended): add `job_type` column ("document" | "plan", default
  "document" for backward compatibility with Phase 1 rows), and
  `parent_job_id` (nullable — the Phase 1 job a "plan" job was created from).
- `PeriodPlan`: period_no, duration_min, title, objectives[],
  concepts_covered[], sequencing_notes.
- `TeachingPlanSkeleton`: periods: list[PeriodPlan].
- `PeriodContent`: entry_ticket, teacher_script, blackboard_notes,
  checkpoint_questions[], exit_ticket, homework, mentor_moment — each
  concept-bearing field paired with a `source_ref` where applicable via a
  `grounded_notes: list[ConceptItem]`-style sidecar list (reuses Phase 1's
  `SourceRef`/`ConceptItem` schemas from `app/schemas/extraction.py`).
- `Activity`: type, duration_min, materials[], teacher_instructions,
  success_criteria.
- `Assessment`: mcqs[], short_answer[], long_answer[], numerical[],
  answer_key, rubric.
- `GapAnalysisItem`: misconception (text + source_ref), diagnostic_questions[],
  severity ("low"|"medium"|"high"), remedial_action.
- `TeachingPlan`: job_id, source_job_id, periods: list[{plan: PeriodPlan,
  content: PeriodContent, activities: list[Activity], assessment:
  Assessment}], gap_analysis: list[GapAnalysisItem].

## Error handling

- Same philosophy as Phase 1: any stage's LLM call failing schema
  validation after retries → whole job marked `failed` with diagnostic,
  no partial/silent success.
- `POST /jobs/{id}/plan` on a Phase 1 job that isn't `completed` → 400.
- `POST /jobs/{id}/plan` on an unknown job id → 404.
- All stage transitions update `Job.progress`: 10 (plan skeleton), evenly
  spread 10→80 across periods × 3 sub-stages, 80→95 (gap analysis), 100.

## Testing

- pytest, `uv run pytest`.
- Contract tests per stage module (`planning`, `content`, `activities`,
  `assessment`, `gaps`): mocked OpenRouter responses (valid + invalid JSON),
  asserting schema validation and retry logic.
- Integration test: full Phase 2 pipeline against a small fixture
  `DocumentKnowledgeExtract` (2 periods worth of content), mocked LLM
  responses, asserting job reaches `completed` with a valid
  `TeachingPlan.json`.
- API tests: `POST /jobs/{id}/plan` (happy path, 400 on non-completed
  source job, 404 on unknown id), `GET /jobs/{id}/plan`,
  `GET /jobs/{id}/result`.
- No live-LLM calls in default test run (same `@pytest.mark.live` pattern
  as Phase 1, not exercised here).

## Environment / tooling

Unchanged from Phase 1: `uv`, same `.env` / `OPENROUTER_API_KEY`, same
SQLite job store (schema migration adds two nullable/defaulted columns),
same `storage/` layout (Phase 2 results saved alongside Phase 1 results
under the same job-id-derived path scheme, keyed by the new job's own id).

## Deferred to later phases

- Stage 9 validation engine (schema adherence, hallucination detection,
  cross-period consistency).
- Stage 10 publishing (TeacherKnowledgePackage.json, PDFs, UI).
- Frontend/UI, deployment.
