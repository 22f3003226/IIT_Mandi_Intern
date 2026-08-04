# Teacher AI Platform — Phase 1: Document Intelligence & Knowledge Extraction

Parses an uploaded document (PDF/DOCX/PPTX/TXT), classifies it educationally, and
extracts a structured knowledge representation, exposed via a job-based upload API
with progress streaming.

## Setup

1. Install [uv](https://docs.astral.sh/uv/).
2. Install the system OCR dependency (only needed for scanned PDFs):
   `sudo apt-get install tesseract-ocr` (Debian/Ubuntu) or equivalent for your OS.
3. `uv sync`
4. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
5. Run the API: `uv run uvicorn app.main:app --reload`

## Usage

- `POST /documents` — multipart form with `file` (PDF/DOCX/PPTX/TXT) and optional
  `doc_nature_hint` (`Mostly Text` / `Text with Tables` / `Text with Diagrams/Figures` /
  `Text with Equations` / `Scanned PDF` / `Not Sure`). Returns `{"job_id": "..."}`.
- `GET /jobs/{job_id}` — current status, stage, progress (0-100), and `result_path`
  once `status` is `completed`.
- `GET /jobs/{job_id}/stream` — Server-Sent Events stream of `{"stage", "progress",
  "status"}` until the job reaches `completed` or `failed`.

## Phase 2: Pedagogical Planning & Generation

- `POST /jobs/{id}/plan` — `id` is a completed Phase 1 document job. Starts the
  Stage 4-8 pipeline (period planning, content, activities, assessment, gap
  analysis) as a new background job and returns that new plan job's status
  (`{"id", "status", "stage", "progress", "error", "result_path"}`).
- `GET /jobs/{id}/plan` — `id` is a plan job. Returns the `TeachingPlan.json`
  body once the plan job's `status` is `completed`; `400` if `id` is not a plan
  job or isn't completed yet.
- `GET /jobs/{id}/result` — generic result fetch that works for both document
  jobs (`DocumentKnowledgeExtract.json`) and plan jobs (`TeachingPlan.json`);
  returns whatever JSON is at the job's `result_path` once `status` is
  `completed`.

Stage 4 (period planning) decides the number and duration of periods
dynamically from the source material rather than assuming a fixed count (FAQ
#3), and every downstream stage — content, activities, assessment, and gap
analysis — grounds its prompts in the Phase 1 `KnowledgeExtract` rather than
re-deriving facts from the raw document (FAQ #4).

## Architecture

```
Client -> POST /documents -> Job created (SQLite) -> background pipeline:
  parse (format-routed) -> classify (OpenRouter) -> extract (OpenRouter)
  -> DocumentKnowledgeExtract.json written to storage/files/{job_id}/
Client polls GET /jobs/{id} or streams GET /jobs/{id}/stream for progress.
```

## Testing

`uv run pytest -v` — no live LLM calls; classification/extraction are tested against
fake clients. `pytest -m live` markers are not yet defined in Phase 1 (all tests are
offline).

## Scope

Phase 1 covers document parsing, classification, and knowledge extraction. Phase 2
(implemented above) adds period planning, content/activity/assessment generation, and
gap analysis on top of the Phase 1 knowledge extract. Validation and TKP publishing
remain later phases (see `docs/superpowers/specs/`).

## Known limitations

- Document text sent to the classification and extraction LLM calls is truncated to
  `MAX_DOCUMENT_CHARS` (8000 characters, see `app/classification/prompts.py` and
  `app/extraction/prompts.py`) per call. Very long chapters may have content beyond
  this limit excluded from the generated knowledge extract.
- The same 8000-character truncation (`MAX_CONTEXT_CHARS`) applies to the five Phase 2
  prompt builders (`app/planning/prompts.py`, `app/content/prompts.py`,
  `app/activities/prompts.py`, `app/assessment/prompts.py`, `app/gaps/prompts.py`), so
  very long knowledge extracts or period content may be truncated before reaching the LLM.
