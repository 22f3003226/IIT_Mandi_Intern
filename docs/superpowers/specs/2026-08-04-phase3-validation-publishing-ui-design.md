# Phase 3: Validation, Publishing, Frontend UI, Deployment — Design

Date: 2026-08-04
Status: Approved

## Objective

Close out the assignment: Stage 9 (validation engine), Stage 10
(TeacherKnowledgePackage assembly + PDF exports), a minimal frontend to
drive the whole pipeline, and a deployed prototype (mandatory per Task
Intern-2.md section 5). Builds on Phase 1 (`document` job) and Phase 2
(`plan` job), which are already merged to `master`.

## Requirements traceability

| Assignment requirement | Covered by |
|---|---|
| Stage 9: Validation (schema, hallucination, missing objectives, consistency) | `app/validation/` |
| Stage 10: Publishing (TKP json + PDFs) | `app/publishing/` |
| Simple UI to evaluate generated content | `frontend/` |
| Deployed, working prototype (mandatory) | HF Spaces Docker Space |
| Streaming progress API | reuses existing `GET /jobs/{id}/stream` |

FAQ constraints honored:
- Hallucination = "not backed by the primary source" (FAQ #4): the judge
  prompt checks generated content against `KnowledgeExtract`, not the raw
  document text. Secondary-source pedagogy (analogies, activity ideas) is
  allowed and not flagged as long as it doesn't introduce new subject
  matter.

## Architecture

```
Client (frontend/)
  │  POST /jobs/{plan_job_id}/publish   (plan_job_id = a completed "plan" job)
  ▼
FastAPI endpoint (app/api/publish.py)
  │  loads Phase 2 TeachingPlan + Phase 1 DocumentKnowledgeExtract via result_path
  │  creates new Job row (job_type="publish", parent_job_id=plan_job_id)
  ▼
Background pipeline (app/jobs/pipeline_publish.py)
  │
  ├─ Stage 9a: rule-based validation (app/validation/rules.py, no LLM)
  │     - every period has >=1 objective
  │     - every plan-level objective covered by some period's concepts_covered
  │     - no duplicate period titles
  │     - no blank required text fields (scripts, notes, tickets)
  │
  ├─ Stage 9b: LLM judge (app/validation/judge.py, one call for the whole plan)
  │     TeachingPlan + KnowledgeExtract → judge prompt →
  │     list of {severity, location, description} for: hallucinated claims
  │     (not traceable to KnowledgeExtract), missing objectives/concepts,
  │     cross-period inconsistencies. Same retry-on-invalid-JSON pattern as
  │     other stages (MAX_RETRIES=2, schema-repair follow-up).
  │
  │     Merge 9a + 9b findings into one ValidationReport.
  │
  ├─ Stage 10a: assemble TeacherKnowledgePackage (app/publishing/assemble.py)
  │     doc metadata + classification + knowledge + teaching plan +
  │     gap_analysis + validation_report → one TeacherKnowledgePackage
  │
  ├─ Stage 10b: render PDFs (app/publishing/pdf.py, fpdf2 — already a dep)
  │     - lesson-plan.pdf: periods, objectives, sequencing
  │     - teacher-guide.pdf: scripts, blackboard notes, activities, mentor moments
  │     - assessment-book.pdf: MCQs/short/long/numerical, answer keys, rubrics
  │
  └─ save TKP json + 3 PDFs to storage, update job (status=completed, result_path)

GET /jobs/{job_id}/publish              → TKP json
GET /jobs/{job_id}/publish/pdf/{kind}   → streams one PDF (kind: lesson-plan|teacher-guide|assessment-book)
```

Move `fpdf2` from `[dependency-groups].dev` to `[project].dependencies` in
`pyproject.toml` — it's used by runtime code now, not just test fixtures.

## Data model (`app/schemas/publishing.py`)

```python
class ValidationIssue(BaseModel):
    severity: str          # "critical" | "warning" | "info"
    category: str          # "hallucination" | "missing_objective" | "inconsistency" | "schema"
    location: str          # e.g. "period-3" or "plan"
    description: str

class ValidationReport(BaseModel):
    issues: list[ValidationIssue]
    passed: bool            # True if no "critical" issues

class TeacherKnowledgePackage(BaseModel):
    job_id: str
    source_job_id: str      # document job id
    plan_job_id: str        # plan job id
    classification: ClassificationResult
    knowledge: KnowledgeExtract
    teaching_plan: TeachingPlan
    validation_report: ValidationReport
```

## API additions (`app/api/publish.py`)

Same guard pattern as `app/api/plans.py`: 404 if job missing, 400 if
wrong job_type/not completed/unreadable result. `POST` creates the job
and schedules the background task; `GET` endpoints require
`status == "completed"`.

## Frontend (`frontend/`)

React + Vite + TypeScript + Tailwind + shadcn/ui, dark theme
(`/minimalist-ui`: editorial, warm monochrome, flat, no gradients/heavy
shadows). React Query for polling/mutations. No router — single-page
wizard driven by local state + job id in a URL query param (bookmarkable,
no auth/job-history list — YAGNI).

Steps: **Upload** (file input, POST `/jobs`) → **Processing** (progress
bar off existing SSE stream, chained through document→plan→publish
automatically) → **Result** (tabs: Overview / Periods / Assessments /
Gap Analysis / Validation Report, plus 3 PDF download buttons).

Use shadcn mcp for primitives (tabs, card, progress, button, badge for
severity) and 21st mcp for layout/composition reference. Run `/gpt-taste`
and `/impeccable` passes on the result screen before considering it done
— avoid generic AI-slop layout (centered card soup, default shadows).

## Deployment

Single Hugging Face Spaces Docker Space. Multi-stage `Dockerfile`:
1. `node:20-alpine` stage — `npm ci && npm run build` in `frontend/`
2. `python:3.11-slim` stage — `uv sync`, copy `app/`, copy built
   frontend `dist/` into a static dir, `COPY` into image
3. FastAPI mounts the built frontend as static files at `/` (catch-all
   fallback to `index.html` since it's a single-page app with no
   client-side routes to worry about); API routes keep their existing
   paths (`/jobs/...`, `/health`).
4. `CMD uvicorn app.main:app --host 0.0.0.0 --port 7860` (HF Spaces
   requires port 7860).

README gets: setup instructions, architecture diagram (mermaid),
orchestration explanation (10-stage pipeline, retry-on-invalid-JSON
pattern, grounding via source_ref), HF Spaces deploy steps.

## Error handling

Same three-level guard hierarchy already used in `plans.py` (404 → 400
precondition → 400 validation). Publish pipeline catches exceptions same
as `run_plan_pipeline`: logs, sets `status="failed"`, `error=str(exc)`.
A "failed" validation (critical issues found) is NOT a pipeline failure —
`ValidationReport.passed=False` still produces a completed job with a
report the user can read; only unexpected exceptions fail the job.

## Testing

- `app/validation/rules.py`: pure unit tests, no mocking needed
  (deterministic input/output).
- `app/validation/judge.py`: unit tests with mocked LLM client, same
  pattern as existing stage tests (`tests/test_planning.py` etc.).
- `app/jobs/pipeline_publish.py`: integration test with mocked LLM judge
  call, asserts TKP json + all 3 PDF files exist and TKP parses back into
  `TeacherKnowledgePackage`.
- Frontend: manual check via `npm run dev` against a live backend run
  (upload → processing → result screen), no automated test suite — not
  requested, deadline-scoped.

## Out of scope

- Job history / multi-user auth on the frontend.
- Per-claim (as opposed to per-plan) LLM validation calls.
- Multi-agent framework/LangChain — orchestration stays the existing
  custom retry-on-invalid-JSON pipeline pattern used since Phase 1/2.
