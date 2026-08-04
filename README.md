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

This is Phase 1 only: document parsing, classification, and knowledge extraction.
Teaching plan/content/activity/assessment generation, validation, and TKP publishing
are later phases (see `docs/superpowers/specs/`).
