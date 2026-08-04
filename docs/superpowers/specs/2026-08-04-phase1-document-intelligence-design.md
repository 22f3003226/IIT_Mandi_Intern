# Phase 1: Document Intelligence & Knowledge Extraction — Design

Date: 2026-08-04
Status: Approved

## Objective

Build the first three stages of the Teacher AI Platform pipeline: parse an uploaded
educational document, classify it, and extract a structured knowledge representation.
Output is a `DocumentKnowledgeExtract.json`, the precursor artifact consumed by Phase 2
(teaching planning/content generation) and eventually assembled into the full
`TeacherKnowledgePackage.json` in Phase 3.

Out of scope for Phase 1: teaching plan generation, activity/assessment generation,
learning gap analysis, validation engine, publishing, frontend UI. Those are later phases.

## Requirements traceability

| Assignment stage | Covered by |
|---|---|
| Stage 1: Document Intelligence | `parsers/` + parser router |
| Stage 2: Educational Classification | `classification/` |
| Stage 3: Knowledge Extraction | `extraction/` |
| Streaming Progress API | `jobs/` + SSE endpoint |

FAQ constraints honored:
- No fixed template; depth/complexity adapts to grade/subject (classification feeds
  extraction prompt with document-specific context, not hardcoded rules).
- Cost-aware routing via user-supplied document-nature hint (FAQ #7): Mostly Text /
  Text with Tables / Text with Diagrams-Figures / Text with Equations / Scanned PDF /
  Not Sure — combined with heuristics (embedded image count, page count) to pick parser
  strategy.
- Extraction stays grounded in the primary source; every extracted concept/definition/etc.
  carries a source reference (section/page) to support later hallucination validation
  (Phase 3, per FAQ #4).
- No mandatory model/provider; OpenRouter used for flexibility per FAQ #6.

## Architecture

```
Client
  │  POST /documents (file + optional doc-nature hint)
  ▼
FastAPI Upload endpoint
  │  creates Job row (SQLite), stores original file on disk
  │  schedules background asyncio task
  ▼
Background pipeline task
  │
  ├─ Stage 1: Parser Router
  │     picks parser by extension + doc-nature hint + heuristics
  │     (pdfplumber/PyMuPDF for PDF, python-docx, python-pptx, plain read for .txt)
  │     → ParsedDocument (sections, headings, tables, figures, equations, metadata)
  │
  ├─ Stage 2: Classification (OpenRouter LLM call)
  │     ParsedDocument → ClassificationResult
  │     {subject, grade, difficulty, topic, chapter, category, language}
  │     Pydantic schema validation; retry with schema-repair prompt on failure
  │
  ├─ Stage 3: Knowledge Extraction (OpenRouter LLM call)
  │     ParsedDocument + ClassificationResult → KnowledgeExtract
  │     {objectives, prerequisites, concepts, definitions, formulae, keywords,
  │      examples, applications, misconceptions}, each item source-referenced
  │     Pydantic schema validation; retry with schema-repair prompt on failure
  │
  └─ Persist DocumentKnowledgeExtract.json (Parsed + Classification + Extraction)
        to filesystem; update Job status = completed (or failed + reason)

Client polls GET /jobs/{id} or streams GET /jobs/{id}/stream (SSE)
  → {"stage": "...", "progress": <0-100>}
```

## Components

- **`parsers/`** — one module per format, each returns a common `ParsedDocument`
  Pydantic model. Router selects parser using file extension, the user's doc-nature
  hint, and lightweight heuristics (embedded image count via PyMuPDF, page count).
  Scanned PDFs route to OCR fallback (pytesseract) only when needed.
- **`classification/`** — prompt template + Pydantic output schema + OpenRouter call
  wrapper with retry-on-invalid-JSON.
- **`extraction/`** — prompt template + Pydantic output schema + OpenRouter call
  wrapper with retry-on-invalid-JSON. Prompt includes classification context so
  depth/tone adapts to grade and subject.
- **`jobs/`** — job lifecycle: create, update progress/stage, mark completed/failed.
  SQLite-backed. Background task runner (asyncio, in-process — no external queue).
- **`api/`** — FastAPI routes: `POST /documents`, `GET /jobs/{id}`,
  `GET /jobs/{id}/stream` (SSE).
- **`storage/`** — filesystem layout for uploaded originals and output JSON; paths
  tracked in SQLite job row.

## Data model (high level)

- `Job`: id, status (queued/running/completed/failed), current_stage, progress (0-100),
  file_path, result_path, error, created_at, updated_at.
- `ParsedDocument`: sections[], headings[], tables[], figures[], equations[], metadata
  (page_count, format, detected_language, etc.).
- `ClassificationResult`: subject, grade, difficulty, topic, chapter, category, language.
- `KnowledgeExtract`: learning_objectives[], prerequisites[], concepts[], definitions[],
  formulae[], keywords[], examples[], applications[], misconceptions[] — each entry
  includes a `source_ref` (section/page pointer) for traceability.
- `DocumentKnowledgeExtract`: wraps the three above, written as the Phase 1 output JSON.

## Error handling

- Parser failure (corrupt file, unsupported content) → job marked `failed` with reason;
  no partial/silent success.
- LLM call returns invalid JSON / fails schema validation → retry up to N times with a
  schema-repair follow-up prompt; still failing → job marked `failed` with diagnostic
  (last raw response saved for debugging).
- All stage transitions update `Job.progress` so the streaming API always reflects real
  state, not estimates.

## Testing

- pytest, using `uv run pytest`.
- Unit tests per parser using fixture documents (1 PDF with a table + equation, 1 DOCX,
  1 PPTX, 1 TXT) — assert `ParsedDocument` structure is correctly populated.
- Contract tests for classification/extraction: mocked OpenRouter responses (valid and
  invalid JSON) — assert schema validation and retry logic behave correctly.
- Integration test: full pipeline against one sample NCERT-style PDF fixture, using a
  recorded/mocked LLM response, asserting the job reaches `completed` with a valid
  `DocumentKnowledgeExtract.json`.
- No live-LLM calls in default CI test run; a separately marked `@pytest.mark.live`
  test exists for manual smoke-testing against the real OpenRouter API.

## Environment / tooling

- `uv` for venv + dependency management (`pyproject.toml`).
- `.env` for `OPENROUTER_API_KEY` (not committed; `.env.example` provided).
- SQLite file for job/metadata storage; local `storage/` directory for files — both
  gitignored, swappable for Postgres/S3 in a later phase without changing the pipeline
  interfaces.

## Deferred to later phases

- Frontend/UI for upload + viewing results.
- Teaching planner, content/activity/assessment generation (Phase 2).
- Validation engine, TKP assembly/publishing, PDF exports (Phase 3).
- Deployment/hosting decision (mandatory for final submission, not for Phase 1 dev).
