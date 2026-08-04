---
title: Teacher AI Platform
emoji: 📚
colorFrom: gray
colorTo: blue
sdk: gradio
sdk_version: 6.22.0
python_version: "3.11"
app_file: app_gradio.py
pinned: false
license: mit
---

# Teacher AI Platform

An AI system that turns a raw educational document (a textbook chapter, a
lecture PDF, a set of slides) into a classroom-ready **Teacher Knowledge
Package (TKP)**: a multi-period teaching plan with scripts, activities,
assessments, a learning-gap analysis, and an automated validation report,
all traceable back to the source document.

Built for the AI Engineer Assignment (see `Task Intern-2.md` and `FAQ .md`
in this repo for the original brief).

**Live demo:** _add your Hugging Face Space URL here once deployed_

## What it does

You upload a document. The system:

1. Parses it, preserving structure: headings, tables, figures, equations
   (Stage 1).
2. Classifies it (subject, grade, difficulty, topic, chapter, category,
   language) (Stage 2).
3. Extracts a structured knowledge representation: learning objectives,
   prerequisites, concepts, definitions, formulae, keywords, examples,
   applications, and common misconceptions, each pointing back to a page
   or section of the source (Stage 3).
4. Plans a multi-period teaching sequence. The number and length of
   periods is decided from the content itself, not a fixed template
   (Stage 4).
5. Generates full classroom material for every period: entry tickets,
   teacher scripts, blackboard notes, checkpoint questions, exit tickets,
   homework, and a motivational "mentor moment" (Stage 5).
6. Designs activities (demonstrations, role play, experiments) with
   duration, materials, instructions, and success criteria (Stage 6).
7. Builds assessments: MCQs, short/long answer, numerical problems,
   answer keys, and rubrics (Stage 7).
8. Runs a learning-gap analysis: likely misconceptions, diagnostic
   questions, severity, and remedial actions (Stage 8).
9. Validates the whole package. A deterministic rule pass, plus an
   LLM-judge pass that checks every generated claim against the extracted
   source knowledge and flags anything that looks hallucinated, missing,
   or inconsistent across periods (Stage 9).
10. Publishes the final `TeacherKnowledgePackage.json`, along with a
    Lesson Plan PDF, a Teacher Guide PDF, and an Assessment Book PDF
    (Stage 10).

A small React wizard walks through upload, processing, and results, with
live progress streaming at every stage.

## Architecture

```mermaid
graph LR
  U[Client / Frontend] -->|POST /documents| A[FastAPI]
  A --> P1[Stage 1-3: Document Intelligence]
  P1 -->|POST /jobs/id/plan| P2[Stage 4-8: Planning and Generation]
  P2 -->|POST /jobs/id/publish| P3[Stage 9-10: Validation and Publishing]
  P3 --> DB[(SQLite JobManager)]
  P3 --> FS[(File storage: JSON + PDFs)]
  P1 & P2 & P3 -.->|OpenRouter LLM calls| LLM[(OpenRouter)]
```

Each of the ten stages lives in its own small Python package
(`app/classification/`, `app/extraction/`, `app/planning/`, `app/content/`,
`app/activities/`, `app/assessment/`, `app/gaps/`, `app/validation/`,
`app/publishing/`). Every stage that calls an LLM follows the same shape:
build a grounded prompt, call OpenRouter, validate the response against a
Pydantic schema, and retry once with a schema-repair follow-up prompt if
the JSON comes back invalid or doesn't match the expected shape
(`MAX_RETRIES = 2`).

**Why a custom pipeline instead of LangChain or a multi-agent framework:**
each stage is one function with one job, taking typed input and producing
typed output, with a retry on failure. That's straightforward to test in
isolation (every stage's tests mock only the LLM call and run the real
logic around it) and straightforward to debug when one specific stage
misbehaves. A framework adds a layer between what the code does and what
actually ran, and for ten stages that each do one thing, I didn't see what
that layer would buy me. A three-level job chain (`document` → `plan` →
`publish`, tracked via `job_type`/`parent_job_id` in `app/jobs/manager.py`)
does the orchestration work instead, and each pipeline function
(`app/jobs/pipeline.py`, `pipeline_plan.py`, `pipeline_publish.py`) reports
progress into SQLite as it moves through stages, streamed to the client
over `GET /jobs/{id}/stream` (Server-Sent Events).

**Grounding and anti-hallucination:** every fact-bearing field in the
knowledge extraction schema (`app/schemas/extraction.py`) carries a
`source_ref` back to a page or section of the original document, and that
same `ConceptItem`/`SourceRef` pair is reused, not redefined, by every
downstream stage. Stage 9's LLM-judge (`app/validation/judge.py`) is given
the full teaching plan side by side with the original knowledge extract
and told explicitly: pedagogical framing from outside knowledge, like
analogies or activity ideas, is fine, but new subject-matter facts that
aren't traceable to the source are not.

**Adaptive depth:** nothing here is templated per subject or grade. Stage
4's planner decides period count and length from content volume,
conceptual complexity, and target grade, rather than assuming a fixed
"5 periods of 40 minutes." Classification metadata (subject, grade,
difficulty) flows into every downstream prompt, so a dense STEM chapter
and a narrative humanities passage end up with differently paced
treatment.

## Setup

### Backend

1. Install [uv](https://docs.astral.sh/uv/).
2. Install the system OCR dependency, needed only for scanned PDFs:
   `sudo apt-get install tesseract-ocr` on Debian/Ubuntu, or the
   equivalent for your OS.
3. `uv sync`
4. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. Get one at
   [openrouter.ai](https://openrouter.ai); several models there are free
   to use for development.
5. Run the API: `uv run uvicorn app.main:app --reload`

The API is now at `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies `/documents`
and `/jobs/*` requests to the backend on `:8000` (see
`frontend/vite.config.ts`), so both need to be running for the UI to work
locally.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | required, your OpenRouter API key | _(none)_ |
| `OPENROUTER_MODEL_CLASSIFICATION` | model for Stage 2 | `openai/gpt-4o-mini` |
| `OPENROUTER_MODEL_EXTRACTION` | model for Stage 3 | `openai/gpt-4o-mini` |
| `OPENROUTER_MODEL_PLANNING` | model for Stage 4 | `openai/gpt-4o-mini` |
| `OPENROUTER_MODEL_CONTENT` | model for Stage 5 | `openai/gpt-4o-mini` |
| `OPENROUTER_MODEL_ACTIVITIES` | model for Stage 6 | `openai/gpt-4o-mini` |
| `OPENROUTER_MODEL_ASSESSMENT` | model for Stage 7 | `openai/gpt-4o-mini` |
| `OPENROUTER_MODEL_GAPS` | model for Stage 8 | `openai/gpt-4o-mini` |
| `OPENROUTER_MODEL_VALIDATION` | model for Stage 9's LLM-judge | `openai/gpt-4o-mini` |
| `DB_PATH` | SQLite database file | `storage/app.db` |
| `STORAGE_DIR` | uploaded files and generated JSON/PDFs | `storage/files` |

Any of the eight model variables can point at a different OpenRouter model
per stage. Classification and extraction are cheap and run fine on a small
model; planning or validation may be worth a stronger one.

## API reference

### Phase 1: Document Intelligence

- `POST /documents`: multipart form with `file` (PDF/DOCX/PPTX/TXT) and an
  optional `doc_nature_hint` (`Mostly Text`, `Text with Tables`,
  `Text with Diagrams/Figures`, `Text with Equations`, `Scanned PDF`, or
  `Not Sure`, used to route to a lighter or heavier parsing strategy).
  Returns `{"job_id": "..."}`.
- `GET /jobs/{job_id}`: current status, stage, progress (0-100), and
  `result_path` once `status` is `completed`.
- `GET /jobs/{job_id}/stream`: Server-Sent Events stream of
  `{"stage", "progress", "status"}` until the job reaches `completed` or
  `failed`.
- `GET /jobs/{job_id}/result`: generic result fetch, works for document,
  plan, or publish jobs alike, returning whatever JSON sits at that job's
  `result_path` once it's completed.

### Phase 2: Pedagogical Planning & Generation

- `POST /jobs/{id}/plan`: `id` is a completed document job. Starts the
  Stage 4-8 pipeline as a new background job and returns that job's
  status.
- `GET /jobs/{id}/plan`: `id` is a plan job. Returns `TeachingPlan.json`
  once completed; `400` if `id` isn't a completed plan job.

### Phase 3: Validation & Publishing

- `POST /jobs/{plan_job_id}/publish`: `plan_job_id` is a completed plan
  job. Starts the Stage 9-10 pipeline (validation, TKP assembly, PDF
  rendering) as a new background job.
- `GET /jobs/{id}/publish`: `id` is a publish job. Returns
  `TeacherKnowledgePackage.json` once completed; `400` if `id` isn't a
  completed publish job or its result is unreadable.
- `GET /jobs/{id}/publish/pdf/{kind}`: `kind` is one of `lesson-plan`,
  `teacher-guide`, `assessment-book`. Streams the corresponding PDF;
  `400` for an unknown `kind`, `404` if the job or file isn't found.

**Important:** validation issues, including `critical` severity ones, are
recorded in the package's `validation_report` but never fail the publish
job. The job always completes with a full `TeacherKnowledgePackage.json`
and all three PDFs; `validation_report.passed` tells the caller whether
anything needs a second look.

## Sample outputs

Two sample `TeacherKnowledgePackage.json` files, generated by running the
full pipeline end to end on real documents, live in `/samples`. See that
folder's own README for how they were produced and how to regenerate more.

## Testing

`uv run pytest -v` runs the full backend suite offline. Every LLM call in
every test is mocked, so no OpenRouter credits are spent and no network
access is required to verify pipeline logic, job chaining, retry behavior,
and API contracts.

## Known limitations

- Document text sent to any LLM-calling stage is truncated to a per-stage
  character limit (`MAX_DOCUMENT_CHARS` / `MAX_CONTEXT_CHARS`, typically
  8000 to 12000 characters, see each stage's `prompts.py`) before being
  sent to the model. A very long chapter may have content beyond that
  limit excluded from what the LLM sees for that call.
- The retry loops across the generation stages catch invalid-JSON and
  schema-validation errors but not transient network errors (rate limits,
  timeouts, 5xx from OpenRouter). A rate-limit hit mid-job currently fails
  the whole job rather than retrying the one call.
- No authentication or multi-user job history. This is a single-tenant
  prototype, by design, for the scope of this assignment.

## Deployment (Hugging Face Spaces)

The live demo runs on the **Gradio** SDK, not Docker. Docker Spaces on
Hugging Face require a PRO subscription even on the free CPU tier;
Gradio Spaces don't. `app_gradio.py` at the repo root wraps the same
pipeline (`app/classification/`, `app/extraction/`, `app/planning/`, and
so on) as a single-request Gradio demo: upload a document, get back a
summary, the `TeacherKnowledgePackage.json`, and the three PDFs. It calls
the pipeline stage functions directly and synchronously, skipping the job
queue and SSE streaming that the FastAPI app uses, since a demo Space only
needs to handle one request at a time.

To deploy:

```bash
hf auth login                                   # your HF token
hf repo create <space-name> --type space --sdk gradio
git remote add hf https://huggingface.co/spaces/<your-username>/<space-name>
git push hf main
hf spaces secrets set OPENROUTER_API_KEY <your-key> <your-username>/<space-name>
```

The Space picks up `requirements.txt` (pip, not `uv`, since that's what
the Gradio SDK expects) and the `sdk`/`app_file` fields in this README's
front matter, and starts serving automatically.

The FastAPI + React app (everything described above) still works exactly
as documented if you'd rather self-host the full version, with the job
queue, streaming progress, and the wizard UI, on any Docker-capable host:
Render, Fly.io, a VPS, or a paid HF Space. The included `Dockerfile` is a
two-stage build (a `node:20-alpine` stage compiles the frontend, its
`frontend/dist/` output gets copied into a `python:3.11-slim` runtime
image alongside the backend) that serves both the wizard UI and the API
from one container on port 7860, running as a non-root user.

## Project structure

```
app/
  classification/   Stage 2, subject/grade/difficulty classification
  extraction/        Stage 3, knowledge extraction (objectives, concepts, ...)
  planning/          Stage 4, teaching planner
  content/           Stage 5, classroom content generation
  activities/        Stage 6, activity generation
  assessment/        Stage 7, assessment generation
  gaps/              Stage 8, learning gap analysis
  validation/        Stage 9, rule-based + LLM-judge validation
  publishing/        Stage 10, TKP assembly + PDF rendering
  parsers/           Stage 1, PDF/DOCX/PPTX/TXT parsing
  jobs/              job manager + pipeline orchestration
  api/               FastAPI routers
  schemas/           Pydantic models shared across stages
  llm/               OpenRouter client wrapper
frontend/            React + Vite + TypeScript upload/results wizard
tests/               pytest suite, offline (all LLM calls mocked)
samples/             sample TeacherKnowledgePackage.json outputs
```

## License

MIT, see `LICENSE`.
