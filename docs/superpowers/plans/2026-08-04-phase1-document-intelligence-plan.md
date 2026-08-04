# Phase 1: Document Intelligence & Knowledge Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working backend pipeline that parses an uploaded document (PDF/DOCX/PPTX/TXT), classifies it educationally, and extracts a structured knowledge representation, exposed via a FastAPI upload + polling/SSE-streaming job API.

**Architecture:** FastAPI app with an upload endpoint that creates a SQLite-backed `Job`, then runs a 3-stage pipeline (parse → classify → extract) as an in-process asyncio background task, writing `DocumentKnowledgeExtract.json` to local filesystem storage. Classification and extraction call OpenRouter with Pydantic schema validation and retry-on-invalid-JSON.

**Tech Stack:** Python 3.11+, `uv` (env/deps), FastAPI, Pydantic v2, pydantic-settings, sqlite3 (stdlib), pdfplumber + PyMuPDF (+ pytesseract OCR fallback) for PDF, python-docx, python-pptx, httpx (OpenRouter calls), pytest.

## Global Constraints

- Every extracted knowledge item must carry a `source_ref` (page/section) — grounding requirement from spec (FAQ #4).
- No fixed period/template assumptions in this phase (not applicable yet — Phase 2 concern), but classification/extraction prompts must not hardcode subject-specific logic; they must work across STEM and Humanities documents.
- No live LLM calls in the default test suite — all classification/extraction tests use fake/mocked clients.
- Parser output for every format must conform to the single shared `ParsedDocument` schema (defined in Task 2) — every later task depends on this exact shape.
- Uploaded files and generated artifacts stay under `storage/` (gitignored); job metadata in a SQLite file, also gitignored.

---

### Task 1: Project scaffolding (uv, config, dirs)

**Files:**
- Create: `pyproject.toml` (via `uv init`/`uv add`)
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `.env.example`
- Create: `.gitignore`
- Test: `tests/test_config.py`
- Test: `tests/__init__.py` (empty, makes tests a package for consistent imports)

**Interfaces:**
- Produces: `app.config.settings` — a `Settings` instance with fields `openrouter_api_key: str`, `openrouter_model_classification: str`, `openrouter_model_extraction: str`, `db_path: str`, `storage_dir: str`.

- [ ] **Step 1: Initialize the project with uv**

```bash
cd /home/prince23/Mandi
uv init --name teacher-ai-platform --no-readme --python 3.11
rm -f hello.py main.py  # remove uv init's stub script if created
mkdir -p app tests storage
touch app/__init__.py tests/__init__.py
```

- [ ] **Step 2: Add runtime dependencies**

```bash
uv add fastapi "uvicorn[standard]" pydantic pydantic-settings python-docx python-pptx pdfplumber pymupdf httpx python-multipart pytesseract pillow
uv add --dev pytest fpdf2
```

- [ ] **Step 3: Write `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    openrouter_api_key: str = ""
    openrouter_model_classification: str = "openai/gpt-4o-mini"
    openrouter_model_extraction: str = "openai/gpt-4o-mini"
    db_path: str = "storage/app.db"
    storage_dir: str = "storage/files"


settings = Settings()
```

- [ ] **Step 4: Write `.env.example`**

```
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL_CLASSIFICATION=openai/gpt-4o-mini
OPENROUTER_MODEL_EXTRACTION=openai/gpt-4o-mini
DB_PATH=storage/app.db
STORAGE_DIR=storage/files
```

- [ ] **Step 5: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
storage/
.env
*.db
```

- [ ] **Step 6: Write the failing test**

```python
# tests/test_config.py
from app.config import Settings


def test_settings_have_expected_defaults():
    settings = Settings(_env_file=None)
    assert settings.openrouter_model_classification == "openai/gpt-4o-mini"
    assert settings.db_path == "storage/app.db"
    assert settings.storage_dir == "storage/files"
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app'` or similar, since step 3 hasn't run yet if done out of order — otherwise this step should already pass since Step 3 precedes it; run anyway to confirm the file is wired correctly)

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock app/__init__.py app/config.py tests/__init__.py tests/test_config.py .env.example .gitignore
git commit -m "chore: scaffold uv project and settings module"
```

---

### Task 2: Core Pydantic schemas

**Files:**
- Create: `app/schemas/__init__.py`
- Create: `app/schemas/parsed_document.py`
- Create: `app/schemas/classification.py`
- Create: `app/schemas/extraction.py`
- Create: `app/schemas/document_knowledge.py`
- Create: `app/schemas/job.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces: `ParsedDocument` (with `.flatten_text() -> str`), `Section`, `TableBlock`, `FigureRef`, `EquationRef`, `DocumentMetadata`, `ClassificationResult`, `SourceRef`, `ConceptItem`, `KnowledgeExtract`, `DocumentKnowledgeExtract`, `JobStatusResponse` — every later task imports these exact names from these exact modules.

- [ ] **Step 1: Write `app/schemas/__init__.py`** (empty file)

- [ ] **Step 2: Write `app/schemas/parsed_document.py`**

```python
from typing import Optional

from pydantic import BaseModel


class Section(BaseModel):
    heading: Optional[str] = None
    level: int = 0
    text: str
    page: Optional[int] = None


class TableBlock(BaseModel):
    page: Optional[int] = None
    rows: list[list[str]]


class FigureRef(BaseModel):
    page: Optional[int] = None
    caption: Optional[str] = None


class EquationRef(BaseModel):
    page: Optional[int] = None
    text: str


class DocumentMetadata(BaseModel):
    source_filename: str
    format: str
    page_count: int
    detected_language: Optional[str] = None


class ParsedDocument(BaseModel):
    metadata: DocumentMetadata
    sections: list[Section] = []
    tables: list[TableBlock] = []
    figures: list[FigureRef] = []
    equations: list[EquationRef] = []

    def flatten_text(self) -> str:
        return "\n\n".join(f"{s.heading or ''}\n{s.text}" for s in self.sections)
```

- [ ] **Step 3: Write `app/schemas/classification.py`**

```python
from pydantic import BaseModel


class ClassificationResult(BaseModel):
    subject: str
    grade: str
    difficulty: str
    topic: str
    chapter: str
    category: str
    language: str
```

- [ ] **Step 4: Write `app/schemas/extraction.py`**

```python
from typing import Optional

from pydantic import BaseModel


class SourceRef(BaseModel):
    page: Optional[int] = None
    section: Optional[str] = None


class ConceptItem(BaseModel):
    text: str
    source_ref: SourceRef


class KnowledgeExtract(BaseModel):
    learning_objectives: list[ConceptItem]
    prerequisites: list[ConceptItem]
    concepts: list[ConceptItem]
    definitions: list[ConceptItem]
    formulae: list[ConceptItem]
    keywords: list[ConceptItem]
    examples: list[ConceptItem]
    applications: list[ConceptItem]
    misconceptions: list[ConceptItem]
```

- [ ] **Step 5: Write `app/schemas/document_knowledge.py`**

```python
from pydantic import BaseModel

from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract
from app.schemas.parsed_document import ParsedDocument


class DocumentKnowledgeExtract(BaseModel):
    parsed_document: ParsedDocument
    classification: ClassificationResult
    knowledge: KnowledgeExtract
```

- [ ] **Step 6: Write `app/schemas/job.py`**

```python
from typing import Optional

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    id: str
    status: str
    stage: Optional[str] = None
    progress: int
    error: Optional[str] = None
    result_path: Optional[str] = None
```

- [ ] **Step 7: Write the failing test**

```python
# tests/test_schemas.py
from app.schemas.classification import ClassificationResult
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.schemas.extraction import ConceptItem, KnowledgeExtract, SourceRef
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section


def test_parsed_document_flatten_text_joins_sections():
    doc = ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[
            Section(heading="Intro", text="Body one."),
            Section(heading=None, text="Body two."),
        ],
    )
    flat = doc.flatten_text()
    assert "Intro" in flat
    assert "Body one." in flat
    assert "Body two." in flat


def test_document_knowledge_extract_round_trips_json():
    doc = ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
    )
    classification = ClassificationResult(
        subject="Physics", grade="9", difficulty="medium", topic="Motion",
        chapter="Laws of Motion", category="STEM", language="English",
    )
    knowledge = KnowledgeExtract(
        learning_objectives=[ConceptItem(text="Understand inertia", source_ref=SourceRef(page=1))],
        prerequisites=[], concepts=[], definitions=[], formulae=[],
        keywords=[], examples=[], applications=[], misconceptions=[],
    )
    package = DocumentKnowledgeExtract(parsed_document=doc, classification=classification, knowledge=knowledge)

    raw = package.model_dump_json()
    restored = DocumentKnowledgeExtract.model_validate_json(raw)
    assert restored.classification.subject == "Physics"
    assert restored.knowledge.learning_objectives[0].text == "Understand inertia"
```

- [ ] **Step 8: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.schemas'`) before steps 1-6 exist; run after writing all schema files to confirm pass instead.

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add app/schemas tests/test_schemas.py
git commit -m "feat: add core Pydantic schemas for parsed documents and knowledge extraction"
```

---

### Task 3: Storage module

**Files:**
- Create: `app/storage/__init__.py`
- Create: `app/storage/files.py`
- Test: `tests/test_storage_files.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `save_upload(storage_dir: str, job_id: str, filename: str, file_obj: BinaryIO) -> str`, `save_result_json(storage_dir: str, job_id: str, content: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_files.py
import io
from pathlib import Path

from app.storage.files import save_result_json, save_upload


def test_save_upload_writes_file_under_job_dir(tmp_path):
    content = b"hello world"
    path = save_upload(str(tmp_path), "job-1", "doc.txt", io.BytesIO(content))
    assert Path(path).read_bytes() == content
    assert Path(path).parent.name == "job-1"


def test_save_result_json_writes_named_file(tmp_path):
    path = save_result_json(str(tmp_path), "job-1", '{"a": 1}')
    assert Path(path).name == "DocumentKnowledgeExtract.json"
    assert Path(path).read_text() == '{"a": 1}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage_files.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.storage'`

- [ ] **Step 3: Write `app/storage/__init__.py`** (empty file)

- [ ] **Step 4: Write `app/storage/files.py`**

```python
import shutil
from pathlib import Path
from typing import BinaryIO


def save_upload(storage_dir: str, job_id: str, filename: str, file_obj: BinaryIO) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    return str(dest_path)


def save_result_json(storage_dir: str, job_id: str, content: str) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "DocumentKnowledgeExtract.json"
    dest_path.write_text(content, encoding="utf-8")
    return str(dest_path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_storage_files.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/storage tests/test_storage_files.py
git commit -m "feat: add filesystem storage helpers for uploads and results"
```

---

### Task 4: Job manager (SQLite) + shared deps module

**Files:**
- Create: `app/jobs/__init__.py`
- Create: `app/jobs/manager.py`
- Create: `app/deps.py`
- Test: `tests/test_jobs_manager.py`

**Interfaces:**
- Consumes: `app.config.settings.db_path`.
- Produces: `JobManager` class with `create_job(file_path: str, job_id: str | None = None) -> str`, `update_job(job_id: str, status=None, stage=None, progress=None, result_path=None, error=None) -> None`, `get_job(job_id: str) -> dict | None`. Module-level `app.deps.job_manager: JobManager` singleton — later tasks (API routes) must access it as `deps.job_manager` (attribute lookup), never `from app.deps import job_manager`, so tests can swap the instance.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jobs_manager.py
from app.jobs.manager import JobManager


def test_create_and_get_job(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path="/tmp/doc.pdf")
    job = manager.get_job(job_id)
    assert job["status"] == "queued"
    assert job["progress"] == 0
    assert job["file_path"] == "/tmp/doc.pdf"


def test_update_job_progress_and_status(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path="/tmp/doc.pdf")
    manager.update_job(job_id, status="running", stage="parsing", progress=10)
    job = manager.get_job(job_id)
    assert job["status"] == "running"
    assert job["stage"] == "parsing"
    assert job["progress"] == 10


def test_get_job_returns_none_for_unknown_id(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    assert manager.get_job("does-not-exist") is None


def test_create_job_with_explicit_id(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path="/tmp/doc.pdf", job_id="fixed-id")
    assert job_id == "fixed-id"
    assert manager.get_job("fixed-id") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_jobs_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jobs'`

- [ ] **Step 3: Write `app/jobs/__init__.py`** (empty file)

- [ ] **Step 4: Write `app/jobs/manager.py`**

```python
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
    updated_at TEXT NOT NULL
);
"""


class JobManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_job(self, file_path: str, job_id: Optional[str] = None) -> str:
        job_id = job_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, stage, progress, file_path, result_path, "
                "error, created_at, updated_at) VALUES (?, 'queued', NULL, 0, ?, NULL, NULL, ?, ?)",
                (job_id, file_path, now, now),
            )
        return job_id

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        progress: Optional[int] = None,
        result_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        fields = {
            "status": status, "stage": stage, "progress": progress,
            "result_path": result_path, "error": error,
        }
        set_fields = {k: v for k, v in fields.items() if v is not None}
        if not set_fields:
            return
        set_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{k} = ?" for k in set_fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",
                (*set_fields.values(), job_id),
            )

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
```

- [ ] **Step 5: Write `app/deps.py`**

```python
from app.config import settings
from app.jobs.manager import JobManager

job_manager = JobManager(settings.db_path)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_jobs_manager.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/jobs app/deps.py tests/test_jobs_manager.py
git commit -m "feat: add SQLite-backed job manager and shared deps module"
```

---

### Task 5: TXT parser

**Files:**
- Create: `app/parsers/__init__.py`
- Create: `app/parsers/base.py`
- Create: `app/parsers/txt_parser.py`
- Create: `tests/conftest.py`
- Test: `tests/test_parsers_txt.py`

**Interfaces:**
- Consumes: `ParsedDocument`, `Section`, `EquationRef`, `DocumentMetadata` from Task 2.
- Produces: `looks_like_heading(line: str) -> bool`, `looks_like_equation(line: str) -> bool` (shared heuristics, reused by every parser); `parse_txt(file_path: str) -> ParsedDocument`. `tests/conftest.py` fixture `sample_txt(tmp_path) -> Path` — later parser test tasks add sibling fixtures to this same file.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
from pathlib import Path

import pytest


@pytest.fixture
def sample_txt(tmp_path: Path) -> Path:
    content = (
        "Introduction\n"
        "This chapter introduces Newtons Laws of Motion.\n\n"
        "Newtons First Law\n"
        "An object at rest stays at rest unless acted upon by a force.\n"
        "F = m * a\n"
    )
    path = tmp_path / "sample.txt"
    path.write_text(content, encoding="utf-8")
    return path
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_parsers_txt.py
from app.parsers.txt_parser import parse_txt


def test_parse_txt_extracts_headings_and_equations(sample_txt):
    result = parse_txt(str(sample_txt))
    assert result.metadata.format == "txt"
    headings = [s.heading for s in result.sections]
    assert "Introduction" in headings
    assert "Newtons First Law" in headings
    assert any("F = m * a" in eq.text for eq in result.equations)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_parsers_txt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.parsers'`

- [ ] **Step 4: Write `app/parsers/__init__.py`** (empty file)

- [ ] **Step 5: Write `app/parsers/base.py`**

```python
import re

EQUATION_PATTERN = re.compile(r"[=∑∫√±≤≥≠^]|\\frac|\\sum|\\int")
HEADING_PATTERN = re.compile(r"^[A-Z0-9][A-Za-z0-9 ,'\-]{2,80}$")


def looks_like_equation(line: str) -> bool:
    return bool(EQUATION_PATTERN.search(line)) and len(line.strip()) < 200


def looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.endswith((".", ",", ";")):
        return False
    return bool(HEADING_PATTERN.match(stripped)) and len(stripped.split()) <= 12
```

- [ ] **Step 6: Write `app/parsers/txt_parser.py`**

```python
from pathlib import Path
from typing import Optional

from app.parsers.base import looks_like_equation, looks_like_heading
from app.schemas.parsed_document import DocumentMetadata, EquationRef, ParsedDocument, Section


def parse_txt(file_path: str) -> ParsedDocument:
    text = Path(file_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    sections: list[Section] = []
    equations: list[EquationRef] = []
    current_heading: Optional[str] = None
    buffer: list[str] = []

    for line in lines:
        if looks_like_equation(line):
            equations.append(EquationRef(text=line.strip()))
        if looks_like_heading(line):
            if buffer:
                sections.append(Section(heading=current_heading, text="\n".join(buffer).strip()))
            buffer = []
            current_heading = line.strip()
        else:
            buffer.append(line)
    if buffer:
        sections.append(Section(heading=current_heading, text="\n".join(buffer).strip()))

    return ParsedDocument(
        metadata=DocumentMetadata(source_filename=Path(file_path).name, format="txt", page_count=1),
        sections=[s for s in sections if s.text],
        equations=equations,
    )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_parsers_txt.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/parsers/__init__.py app/parsers/base.py app/parsers/txt_parser.py tests/conftest.py tests/test_parsers_txt.py
git commit -m "feat: add TXT parser and shared heading/equation heuristics"
```

---

### Task 6: DOCX parser

**Files:**
- Create: `app/parsers/docx_parser.py`
- Modify: `tests/conftest.py` (add `sample_docx` fixture)
- Test: `tests/test_parsers_docx.py`

**Interfaces:**
- Consumes: `looks_like_equation` from Task 5; `ParsedDocument`, `Section`, `TableBlock`, `FigureRef`, `EquationRef`, `DocumentMetadata` from Task 2.
- Produces: `parse_docx(file_path: str) -> ParsedDocument`.

- [ ] **Step 1: Add `sample_docx` fixture to `tests/conftest.py`**

```python
# append to tests/conftest.py
from docx import Document as DocxDocument


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    doc = DocxDocument()
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph("This chapter introduces Newtons Laws of Motion.")
    doc.add_heading("Newtons First Law", level=1)
    doc.add_paragraph("An object at rest stays at rest unless acted upon by a force.")
    doc.add_paragraph("F = m * a")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Term"
    table.cell(0, 1).text = "Definition"
    table.cell(1, 0).text = "Force"
    table.cell(1, 1).text = "A push or pull"
    path = tmp_path / "sample.docx"
    doc.save(path)
    return path
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_parsers_docx.py
from app.parsers.docx_parser import parse_docx


def test_parse_docx_extracts_headings_tables_and_equations(sample_docx):
    result = parse_docx(str(sample_docx))
    assert result.metadata.format == "docx"
    headings = [s.heading for s in result.sections]
    assert "Introduction" in headings
    assert "Newtons First Law" in headings
    assert len(result.tables) == 1
    assert result.tables[0].rows[0] == ["Term", "Definition"]
    assert any("F = m * a" in eq.text for eq in result.equations)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_parsers_docx.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.parsers.docx_parser'`

- [ ] **Step 4: Write `app/parsers/docx_parser.py`**

```python
from pathlib import Path
from typing import Optional

import docx

from app.parsers.base import looks_like_equation
from app.schemas.parsed_document import (
    DocumentMetadata,
    EquationRef,
    FigureRef,
    ParsedDocument,
    Section,
    TableBlock,
)

HEADING_STYLES = {"Heading 1": 1, "Heading 2": 2, "Heading 3": 3, "Title": 1}


def _flush(sections: list[Section], buffer: list[str], heading: Optional[str], level: int) -> None:
    if buffer:
        sections.append(Section(heading=heading, level=level, text="\n".join(buffer).strip()))


def parse_docx(file_path: str) -> ParsedDocument:
    document = docx.Document(file_path)
    sections: list[Section] = []
    equations: list[EquationRef] = []
    current_heading: Optional[str] = None
    current_level = 0
    buffer: list[str] = []

    for para in document.paragraphs:
        text = para.text
        if not text.strip():
            continue
        if looks_like_equation(text):
            equations.append(EquationRef(text=text.strip()))
        style_name = para.style.name if para.style else ""
        if style_name in HEADING_STYLES:
            _flush(sections, buffer, current_heading, current_level)
            buffer = []
            current_heading = text.strip()
            current_level = HEADING_STYLES[style_name]
        else:
            buffer.append(text)
    _flush(sections, buffer, current_heading, current_level)

    tables = [
        TableBlock(rows=[[cell.text for cell in row.cells] for row in table.rows])
        for table in document.tables
    ]
    figures = [FigureRef() for _ in document.inline_shapes]

    return ParsedDocument(
        metadata=DocumentMetadata(source_filename=Path(file_path).name, format="docx", page_count=1),
        sections=sections,
        tables=tables,
        figures=figures,
        equations=equations,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_parsers_docx.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/parsers/docx_parser.py tests/conftest.py tests/test_parsers_docx.py
git commit -m "feat: add DOCX parser"
```

---

### Task 7: PPTX parser

**Files:**
- Create: `app/parsers/pptx_parser.py`
- Modify: `tests/conftest.py` (add `sample_pptx` fixture)
- Test: `tests/test_parsers_pptx.py`

**Interfaces:**
- Consumes: `looks_like_equation` from Task 5; schemas from Task 2.
- Produces: `parse_pptx(file_path: str) -> ParsedDocument`.

- [ ] **Step 1: Add `sample_pptx` fixture to `tests/conftest.py`**

```python
# append to tests/conftest.py
from pptx import Presentation


@pytest.fixture
def sample_pptx(tmp_path: Path) -> Path:
    prs = Presentation()
    layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Newtons Laws"
    slide.placeholders[1].text = "An object at rest stays at rest unless acted upon by a force.\nF = m * a"
    path = tmp_path / "sample.pptx"
    prs.save(path)
    return path
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_parsers_pptx.py
from app.parsers.pptx_parser import parse_pptx


def test_parse_pptx_extracts_slide_sections_and_equations(sample_pptx):
    result = parse_pptx(str(sample_pptx))
    assert result.metadata.format == "pptx"
    assert result.metadata.page_count == 1
    assert result.sections[0].heading == "Newtons Laws"
    assert any("F = m * a" in eq.text for eq in result.equations)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_parsers_pptx.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.parsers.pptx_parser'`

- [ ] **Step 4: Write `app/parsers/pptx_parser.py`**

```python
from pathlib import Path
from typing import Optional

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.parsers.base import looks_like_equation
from app.schemas.parsed_document import (
    DocumentMetadata,
    EquationRef,
    FigureRef,
    ParsedDocument,
    Section,
    TableBlock,
)


def parse_pptx(file_path: str) -> ParsedDocument:
    prs = Presentation(file_path)
    sections: list[Section] = []
    tables: list[TableBlock] = []
    figures: list[FigureRef] = []
    equations: list[EquationRef] = []
    slide_count = 0

    for slide_index, slide in enumerate(prs.slides, start=1):
        slide_count = slide_index
        heading: Optional[str] = None
        body_lines: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text
                if not text.strip():
                    continue
                if shape == slide.shapes.title:
                    heading = text.strip()
                else:
                    body_lines.append(text)
                    for line in text.splitlines():
                        if looks_like_equation(line):
                            equations.append(EquationRef(page=slide_index, text=line.strip()))
            if shape.has_table:
                rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
                tables.append(TableBlock(page=slide_index, rows=rows))
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                figures.append(FigureRef(page=slide_index))
        sections.append(Section(heading=heading, page=slide_index, text="\n".join(body_lines).strip()))

    return ParsedDocument(
        metadata=DocumentMetadata(source_filename=Path(file_path).name, format="pptx", page_count=slide_count),
        sections=sections,
        tables=tables,
        figures=figures,
        equations=equations,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_parsers_pptx.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/parsers/pptx_parser.py tests/conftest.py tests/test_parsers_pptx.py
git commit -m "feat: add PPTX parser"
```

---

### Task 8: PDF parser with OCR fallback

**Files:**
- Create: `app/parsers/ocr.py`
- Create: `app/parsers/pdf_parser.py`
- Modify: `tests/conftest.py` (add `sample_pdf` and `blank_scanned_pdf` fixtures)
- Test: `tests/test_parsers_pdf.py`

**Interfaces:**
- Consumes: `looks_like_equation`, `looks_like_heading` from Task 5; schemas from Task 2.
- Produces: `ocr_page_text(doc: fitz.Document, page_index: int) -> str`; `parse_pdf(file_path: str, doc_nature_hint: Optional[str] = None) -> ParsedDocument` — used directly by the parser router in Task 9.

- [ ] **Step 1: Add PDF fixtures to `tests/conftest.py`**

```python
# append to tests/conftest.py
from fpdf import FPDF


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, "Introduction", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 8, "This chapter introduces Newtons Laws of Motion.")
    pdf.cell(0, 10, "Newtons First Law", ln=True)
    pdf.multi_cell(0, 8, "An object at rest stays at rest unless acted upon by a force.")
    pdf.cell(0, 8, "F = m * a", ln=True)
    path = tmp_path / "sample.pdf"
    pdf.output(str(path))
    return path


@pytest.fixture
def blank_scanned_pdf(tmp_path: Path) -> Path:
    pdf = FPDF()
    pdf.add_page()
    path = tmp_path / "scanned.pdf"
    pdf.output(str(path))
    return path
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_parsers_pdf.py
from unittest.mock import patch

from app.parsers.pdf_parser import parse_pdf


def test_parse_pdf_extracts_headings_and_equations(sample_pdf):
    result = parse_pdf(str(sample_pdf))
    assert result.metadata.format == "pdf"
    headings = [s.heading for s in result.sections]
    assert "Introduction" in headings
    assert any("F = m * a" in eq.text for eq in result.equations)


def test_parse_pdf_triggers_ocr_for_scanned_pdf(blank_scanned_pdf):
    with patch("app.parsers.pdf_parser.ocr_page_text", return_value="OCR extracted text") as mock_ocr:
        result = parse_pdf(str(blank_scanned_pdf), doc_nature_hint="Scanned PDF")
    mock_ocr.assert_called()
    assert result.metadata.page_count == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_parsers_pdf.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.parsers.pdf_parser'`

- [ ] **Step 4: Write `app/parsers/ocr.py`**

```python
import io

import fitz
import pytesseract
from PIL import Image


def ocr_page_text(doc: fitz.Document, page_index: int) -> str:
    page = doc[page_index]
    pix = page.get_pixmap(dpi=200)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(image)
```

- [ ] **Step 5: Write `app/parsers/pdf_parser.py`**

```python
from pathlib import Path
from typing import Optional

import fitz
import pdfplumber

from app.parsers.base import looks_like_equation, looks_like_heading
from app.parsers.ocr import ocr_page_text
from app.schemas.parsed_document import (
    DocumentMetadata,
    EquationRef,
    FigureRef,
    ParsedDocument,
    Section,
    TableBlock,
)

OCR_TRIGGER_CHAR_COUNT = 20


def parse_pdf(file_path: str, doc_nature_hint: Optional[str] = None) -> ParsedDocument:
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        page_texts = [(page.extract_text() or "") for page in pdf.pages]
        tables: list[TableBlock] = []
        for page_index, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                tables.append(TableBlock(page=page_index, rows=[[cell or "" for cell in row] for row in table]))

    total_chars = sum(len(t.strip()) for t in page_texts)
    if doc_nature_hint == "Scanned PDF" or total_chars < OCR_TRIGGER_CHAR_COUNT:
        with fitz.open(file_path) as doc:
            page_texts = [ocr_page_text(doc, i) for i in range(page_count)]

    sections: list[Section] = []
    equations: list[EquationRef] = []
    for page_index, text in enumerate(page_texts, start=1):
        current_heading: Optional[str] = None
        buffer: list[str] = []
        for line in text.splitlines():
            if looks_like_equation(line):
                equations.append(EquationRef(page=page_index, text=line.strip()))
            if looks_like_heading(line):
                if buffer:
                    sections.append(Section(heading=current_heading, page=page_index, text="\n".join(buffer).strip()))
                buffer = []
                current_heading = line.strip()
            else:
                buffer.append(line)
        if buffer:
            sections.append(Section(heading=current_heading, page=page_index, text="\n".join(buffer).strip()))

    figures: list[FigureRef] = []
    with fitz.open(file_path) as doc:
        for page_index in range(len(doc)):
            image_count = len(doc[page_index].get_images())
            figures.extend(FigureRef(page=page_index + 1) for _ in range(image_count))

    return ParsedDocument(
        metadata=DocumentMetadata(source_filename=Path(file_path).name, format="pdf", page_count=page_count),
        sections=[s for s in sections if s.text],
        tables=tables,
        figures=figures,
        equations=equations,
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_parsers_pdf.py -v`
Expected: PASS

Note: this requires the `tesseract-ocr` system binary to be importable by `pytesseract` at runtime for real OCR use; the test above mocks `ocr_page_text` so it does not require the binary to pass. Document this system dependency in the README (Task 15).

- [ ] **Step 7: Commit**

```bash
git add app/parsers/ocr.py app/parsers/pdf_parser.py tests/conftest.py tests/test_parsers_pdf.py
git commit -m "feat: add PDF parser with heuristic OCR fallback for scanned pages"
```

---

### Task 9: Parser router

**Files:**
- Create: `app/parsers/router.py`
- Test: `tests/test_parser_router.py`

**Interfaces:**
- Consumes: `parse_pdf` (Task 8), `parse_docx` (Task 6), `parse_pptx` (Task 7), `parse_txt` (Task 5).
- Produces: `SUPPORTED_EXTENSIONS: set[str]`, `UnsupportedFormatError(ValueError)`, `route_and_parse(file_path: str, doc_nature_hint: Optional[str] = None) -> ParsedDocument` — this is what the pipeline (Task 13) and API (Task 14) call.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parser_router.py
import pytest

from app.parsers.router import UnsupportedFormatError, route_and_parse


def test_router_dispatches_txt_by_extension(sample_txt):
    result = route_and_parse(str(sample_txt))
    assert result.metadata.format == "txt"


def test_router_dispatches_pdf_and_passes_hint(sample_pdf):
    result = route_and_parse(str(sample_pdf), doc_nature_hint="Mostly Text")
    assert result.metadata.format == "pdf"


def test_router_rejects_unsupported_extension(tmp_path):
    bad_file = tmp_path / "notes.xyz"
    bad_file.write_text("hello")
    with pytest.raises(UnsupportedFormatError):
        route_and_parse(str(bad_file))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parser_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.parsers.router'`

- [ ] **Step 3: Write `app/parsers/router.py`**

```python
from pathlib import Path
from typing import Optional

from app.parsers.docx_parser import parse_docx
from app.parsers.pdf_parser import parse_pdf
from app.parsers.pptx_parser import parse_pptx
from app.parsers.txt_parser import parse_txt
from app.schemas.parsed_document import ParsedDocument

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt"}

EXTENSION_MAP = {
    ".docx": parse_docx,
    ".pptx": parse_pptx,
    ".txt": parse_txt,
}


class UnsupportedFormatError(ValueError):
    pass


def route_and_parse(file_path: str, doc_nature_hint: Optional[str] = None) -> ParsedDocument:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(file_path, doc_nature_hint=doc_nature_hint)
    parser = EXTENSION_MAP.get(ext)
    if parser is None:
        raise UnsupportedFormatError(f"Unsupported file extension: {ext}")
    return parser(file_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_parser_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/parsers/router.py tests/test_parser_router.py
git commit -m "feat: add parser router with extension + doc-nature-hint dispatch"
```

---

### Task 10: OpenRouter LLM client

**Files:**
- Create: `app/llm/__init__.py`
- Create: `app/llm/openrouter_client.py`
- Test: `tests/test_openrouter_client.py`

**Interfaces:**
- Produces: `LLMResponseError(Exception)`, `OpenRouterClient` class with `complete_json(model: str, system_prompt: str, user_prompt: str) -> dict`. Used by Tasks 11 and 12.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_openrouter_client.py
import httpx
import pytest

from app.llm.openrouter_client import LLMResponseError, OpenRouterClient


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_complete_json_parses_valid_response(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return DummyResponse({"choices": [{"message": {"content": '{"a": 1}'}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenRouterClient(api_key="test-key")
    result = client.complete_json("model-x", "system", "user")
    assert result == {"a": 1}


def test_complete_json_raises_on_invalid_json(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return DummyResponse({"choices": [{"message": {"content": "not json"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenRouterClient(api_key="test-key")
    with pytest.raises(LLMResponseError):
        client.complete_json("model-x", "system", "user")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_openrouter_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm'`

- [ ] **Step 3: Write `app/llm/__init__.py`** (empty file)

- [ ] **Step 4: Write `app/llm/openrouter_client.py`**

```python
import json
from typing import Optional

import httpx

from app.config import settings


class LLMResponseError(Exception):
    pass


class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = base_url

    def complete_json(self, model: str, system_prompt: str, user_prompt: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"Model did not return valid JSON: {content[:200]}") from exc
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_openrouter_client.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/llm tests/test_openrouter_client.py
git commit -m "feat: add OpenRouter client wrapper with JSON parsing"
```

---

### Task 11: Classification stage

**Files:**
- Create: `app/classification/__init__.py`
- Create: `app/classification/prompts.py`
- Create: `app/classification/classify.py`
- Test: `tests/test_classification.py`

**Interfaces:**
- Consumes: `OpenRouterClient`, `LLMResponseError` (Task 10); `ParsedDocument.flatten_text()` (Task 2); `settings.openrouter_model_classification` (Task 1).
- Produces: `classify(parsed: ParsedDocument, client: Optional[OpenRouterClient] = None) -> ClassificationResult` — any object passed as `client` only needs a `complete_json(model, system_prompt, user_prompt) -> dict` method (duck-typed, so tests can pass a fake). Used by Task 13 (pipeline).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_classification.py
from app.classification.classify import classify
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section


def make_parsed():
    return ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[Section(heading="Newtons First Law", text="An object at rest stays at rest.")],
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete_json(self, model, system_prompt, user_prompt):
        response = self.responses[self.calls]
        self.calls += 1
        return response


def test_classify_returns_valid_result_on_first_try():
    client = FakeClient([{
        "subject": "Physics", "grade": "9", "difficulty": "medium", "topic": "Motion",
        "chapter": "Laws of Motion", "category": "STEM", "language": "English",
    }])
    result = classify(make_parsed(), client=client)
    assert result.subject == "Physics"
    assert client.calls == 1


def test_classify_retries_on_invalid_schema_then_succeeds():
    client = FakeClient([
        {"subject": "Physics"},
        {
            "subject": "Physics", "grade": "9", "difficulty": "medium", "topic": "Motion",
            "chapter": "Laws of Motion", "category": "STEM", "language": "English",
        },
    ])
    result = classify(make_parsed(), client=client)
    assert result.grade == "9"
    assert client.calls == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_classification.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.classification'`

- [ ] **Step 3: Write `app/classification/__init__.py`** (empty file)

- [ ] **Step 4: Write `app/classification/prompts.py`**

```python
SYSTEM_PROMPT = """You are an expert curriculum classifier. Given the text of an educational
document, determine its Subject, Grade level, Difficulty, Topic, Chapter name, Category
(e.g. STEM, Humanities, Language), and Language. Base your answer only on the document
content provided; do not assume a specific curriculum board unless stated. Respond ONLY
with a JSON object with exactly these keys: subject, grade, difficulty, topic, chapter,
category, language."""


def build_user_prompt(document_text: str) -> str:
    return f"Document content:\n\n{document_text[:8000]}"
```

- [ ] **Step 5: Write `app/classification/classify.py`**

```python
from typing import Optional

from pydantic import ValidationError

from app.classification.prompts import SYSTEM_PROMPT, build_user_prompt
from app.config import settings
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.classification import ClassificationResult
from app.schemas.parsed_document import ParsedDocument

MAX_RETRIES = 2


def classify(parsed: ParsedDocument, client: Optional[OpenRouterClient] = None) -> ClassificationResult:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(parsed.flatten_text())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid. Return ONLY a valid JSON "
            "object with keys: subject, grade, difficulty, topic, chapter, category, language."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_classification, SYSTEM_PROMPT, prompt)
            return ClassificationResult.model_validate(raw)
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_classification.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/classification tests/test_classification.py
git commit -m "feat: add educational classification stage with retry-on-invalid-schema"
```

---

### Task 12: Knowledge extraction stage

**Files:**
- Create: `app/extraction/__init__.py`
- Create: `app/extraction/prompts.py`
- Create: `app/extraction/extract.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Consumes: `OpenRouterClient`, `LLMResponseError` (Task 10); `ParsedDocument.flatten_text()`, `KnowledgeExtract`, `ConceptItem`, `SourceRef` (Task 2); `ClassificationResult` (Task 2); `settings.openrouter_model_extraction` (Task 1).
- Produces: `extract(parsed: ParsedDocument, classification: ClassificationResult, client: Optional[OpenRouterClient] = None) -> KnowledgeExtract`. Used by Task 13 (pipeline).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extraction.py
from app.extraction.extract import extract
from app.schemas.classification import ClassificationResult
from app.schemas.parsed_document import DocumentMetadata, ParsedDocument, Section


def make_parsed():
    return ParsedDocument(
        metadata=DocumentMetadata(source_filename="x.txt", format="txt", page_count=1),
        sections=[Section(heading="Newtons First Law", text="An object at rest stays at rest.")],
    )


def make_classification():
    return ClassificationResult(
        subject="Physics", grade="9", difficulty="medium", topic="Motion",
        chapter="Laws of Motion", category="STEM", language="English",
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete_json(self, model, system_prompt, user_prompt):
        response = self.responses[self.calls]
        self.calls += 1
        return response


VALID_EXTRACTION = {
    "learning_objectives": [{"text": "Understand inertia", "source_ref": {"page": 1, "section": "Newtons First Law"}}],
    "prerequisites": [],
    "concepts": [{"text": "Inertia", "source_ref": {"page": 1, "section": "Newtons First Law"}}],
    "definitions": [],
    "formulae": [],
    "keywords": [{"text": "inertia", "source_ref": {"page": 1, "section": None}}],
    "examples": [],
    "applications": [],
    "misconceptions": [],
}


def test_extract_returns_valid_result_on_first_try():
    client = FakeClient([VALID_EXTRACTION])
    result = extract(make_parsed(), make_classification(), client=client)
    assert result.concepts[0].text == "Inertia"
    assert client.calls == 1


def test_extract_retries_on_invalid_schema_then_succeeds():
    client = FakeClient([{"learning_objectives": []}, VALID_EXTRACTION])
    result = extract(make_parsed(), make_classification(), client=client)
    assert result.keywords[0].text == "inertia"
    assert client.calls == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_extraction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.extraction'`

- [ ] **Step 3: Write `app/extraction/__init__.py`** (empty file)

- [ ] **Step 4: Write `app/extraction/prompts.py`**

```python
SYSTEM_PROMPT = """You are an expert educator building a structured knowledge extraction from a
textbook chapter. Given the document text and its classification, extract: learning_objectives,
prerequisites, concepts, definitions, formulae, keywords, examples, applications, and
misconceptions. Every item MUST include a "source_ref" object with a "page" (int or null) and
"section" (string or null) pointing to where it came from in the source document. Do not invent
facts absent from the source document; you may only draw on outside knowledge to phrase
pedagogy, not to add new subject matter. Respond ONLY with a JSON object with exactly these
keys, each an array of objects with "text" and "source_ref": learning_objectives,
prerequisites, concepts, definitions, formulae, keywords, examples, applications,
misconceptions."""


def build_user_prompt(document_text: str, classification: dict) -> str:
    return f"Classification: {classification}\n\nDocument content:\n\n{document_text[:8000]}"
```

- [ ] **Step 5: Write `app/extraction/extract.py`**

```python
from typing import Optional

from pydantic import ValidationError

from app.config import settings
from app.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm.openrouter_client import LLMResponseError, OpenRouterClient
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract
from app.schemas.parsed_document import ParsedDocument

MAX_RETRIES = 2


def extract(
    parsed: ParsedDocument,
    classification: ClassificationResult,
    client: Optional[OpenRouterClient] = None,
) -> KnowledgeExtract:
    client = client or OpenRouterClient()
    user_prompt = build_user_prompt(parsed.flatten_text(), classification.model_dump())

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt if attempt == 0 else (
            user_prompt + "\n\nYour previous response was invalid JSON or missing required "
            "keys. Return ONLY a valid JSON object with the required structure."
        )
        try:
            raw = client.complete_json(settings.openrouter_model_extraction, SYSTEM_PROMPT, prompt)
            return KnowledgeExtract.model_validate(raw)
        except (LLMResponseError, ValidationError) as exc:
            last_error = exc
    raise last_error
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_extraction.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/extraction tests/test_extraction.py
git commit -m "feat: add knowledge extraction stage with source-grounded schema"
```

---

### Task 13: Pipeline orchestration

**Files:**
- Create: `app/jobs/pipeline.py`
- Test: `tests/test_pipeline_integration.py`

**Interfaces:**
- Consumes: `JobManager` (Task 4), `route_and_parse` (Task 9), `classify` (Task 11), `extract` (Task 12), `DocumentKnowledgeExtract` (Task 2), `save_result_json` (Task 3).
- Produces: `async def run_pipeline(job_manager: JobManager, storage_dir: str, job_id: str, file_path: str, doc_nature_hint: Optional[str] = None) -> None` — used by the API layer (Task 14).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline_integration.py
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from app.jobs.manager import JobManager
from app.jobs.pipeline import run_pipeline
from app.schemas.classification import ClassificationResult
from app.schemas.extraction import KnowledgeExtract


def make_classification():
    return ClassificationResult(
        subject="Physics", grade="9", difficulty="medium", topic="Motion",
        chapter="Laws of Motion", category="STEM", language="English",
    )


def make_extraction():
    return KnowledgeExtract(
        learning_objectives=[], prerequisites=[], concepts=[], definitions=[],
        formulae=[], keywords=[], examples=[], applications=[], misconceptions=[],
    )


def test_run_pipeline_completes_job_and_writes_result(tmp_path, sample_txt):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path=str(sample_txt))
    storage_dir = str(tmp_path / "files")

    with patch("app.jobs.pipeline.classify", return_value=make_classification()), \
         patch("app.jobs.pipeline.extract", return_value=make_extraction()):
        asyncio.run(run_pipeline(manager, storage_dir, job_id, str(sample_txt)))

    job = manager.get_job(job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 100
    result_path = Path(job["result_path"])
    assert result_path.exists()
    data = json.loads(result_path.read_text())
    assert data["classification"]["subject"] == "Physics"


def test_run_pipeline_marks_job_failed_on_parser_error(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    bad_path = str(tmp_path / "missing.txt")
    job_id = manager.create_job(file_path=bad_path)
    storage_dir = str(tmp_path / "files")

    asyncio.run(run_pipeline(manager, storage_dir, job_id, bad_path))

    job = manager.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jobs.pipeline'`

- [ ] **Step 3: Write `app/jobs/pipeline.py`**

```python
import asyncio
from typing import Optional

from app.classification.classify import classify
from app.extraction.extract import extract
from app.jobs.manager import JobManager
from app.parsers.router import route_and_parse
from app.schemas.document_knowledge import DocumentKnowledgeExtract
from app.storage.files import save_result_json


async def run_pipeline(
    job_manager: JobManager,
    storage_dir: str,
    job_id: str,
    file_path: str,
    doc_nature_hint: Optional[str] = None,
) -> None:
    try:
        job_manager.update_job(job_id, status="running", stage="parsing", progress=10)
        parsed = await asyncio.to_thread(route_and_parse, file_path, doc_nature_hint)

        job_manager.update_job(job_id, stage="classification", progress=40)
        classification = await asyncio.to_thread(classify, parsed)

        job_manager.update_job(job_id, stage="extraction", progress=70)
        knowledge = await asyncio.to_thread(extract, parsed, classification)

        job_manager.update_job(job_id, stage="packaging", progress=90)
        result = DocumentKnowledgeExtract(parsed_document=parsed, classification=classification, knowledge=knowledge)
        result_path = await asyncio.to_thread(
            save_result_json, storage_dir, job_id, result.model_dump_json(indent=2)
        )

        job_manager.update_job(job_id, status="completed", stage="done", progress=100, result_path=result_path)
    except Exception as exc:
        job_manager.update_job(job_id, status="failed", error=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/jobs/pipeline.py tests/test_pipeline_integration.py
git commit -m "feat: orchestrate parse -> classify -> extract pipeline with job progress tracking"
```

---

### Task 14: FastAPI app and API routes

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/documents.py`
- Create: `app/api/jobs.py`
- Create: `app/main.py`
- Test: `tests/test_api_documents.py`
- Test: `tests/test_api_jobs.py`

**Interfaces:**
- Consumes: `deps.job_manager` (Task 4, accessed via `from app import deps` then `deps.job_manager.*` — never imported by name, so tests can swap the instance), `run_pipeline` (Task 13), `save_upload` (Task 3), `SUPPORTED_EXTENSIONS` (Task 9), `JobStatusResponse` (Task 2).
- Produces: `POST /documents` → `{"job_id": str}`; `GET /jobs/{job_id}` → `JobStatusResponse`; `GET /jobs/{job_id}/stream` → SSE stream of `{"stage", "progress", "status"}`; FastAPI `app` instance in `app/main.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_documents.py
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.jobs.manager import JobManager
from app.main import app


def test_upload_document_creates_job(tmp_path, monkeypatch, sample_txt):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))

    with patch("app.api.documents.run_pipeline", new=AsyncMock()):
        client = TestClient(app)
        with open(sample_txt, "rb") as f:
            response = client.post("/documents", files={"file": ("sample.txt", f, "text/plain")})

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    assert deps.job_manager.get_job(job_id) is not None


def test_upload_document_rejects_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "files"))
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    client = TestClient(app)
    response = client.post("/documents", files={"file": ("notes.xyz", b"hello", "text/plain")})
    assert response.status_code == 400
```

```python
# tests/test_api_jobs.py
from fastapi.testclient import TestClient

from app import deps
from app.jobs.manager import JobManager
from app.main import app


def test_get_job_returns_status(tmp_path):
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = deps.job_manager.create_job(file_path="/tmp/x.txt")

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_get_job_returns_404_for_unknown(tmp_path):
    deps.job_manager = JobManager(str(tmp_path / "jobs.db"))
    client = TestClient(app)
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_documents.py tests/test_api_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api'` (or `app.main`)

- [ ] **Step 3: Write `app/api/__init__.py`** (empty file)

- [ ] **Step 4: Write `app/api/documents.py`**

```python
import asyncio
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app import deps
from app.config import settings
from app.jobs.pipeline import run_pipeline
from app.parsers.router import SUPPORTED_EXTENSIONS
from app.storage.files import save_upload

router = APIRouter()


@router.post("/documents")
async def upload_document(file: UploadFile = File(...), doc_nature_hint: Optional[str] = Form(None)):
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")

    job_id = str(uuid.uuid4())
    file_path = save_upload(settings.storage_dir, job_id, file.filename, file.file)
    deps.job_manager.create_job(file_path=file_path, job_id=job_id)

    asyncio.create_task(
        run_pipeline(deps.job_manager, settings.storage_dir, job_id, file_path, doc_nature_hint)
    )
    return {"job_id": job_id}
```

- [ ] **Step 5: Write `app/api/jobs.py`**

```python
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import deps
from app.schemas.job import JobStatusResponse

router = APIRouter()


def _to_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        id=job["id"], status=job["status"], stage=job["stage"],
        progress=job["progress"], error=job["error"], result_path=job["result_path"],
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    job = deps.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_response(job)


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_generator():
        while True:
            job = deps.job_manager.get_job(job_id)
            if job is None:
                yield f"data: {json.dumps({'error': 'not found'})}\n\n"
                return
            payload = {"stage": job["stage"], "progress": job["progress"], "status": job["status"]}
            yield f"data: {json.dumps(payload)}\n\n"
            if job["status"] in ("completed", "failed"):
                return
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 6: Write `app/main.py`**

```python
from fastapi import FastAPI

from app.api import documents, jobs

app = FastAPI(title="Teacher AI Platform - Phase 1")
app.include_router(documents.router)
app.include_router(jobs.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_documents.py tests/test_api_jobs.py -v`
Expected: PASS

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS (all tests from Tasks 1-14)

- [ ] **Step 9: Commit**

```bash
git add app/api app/main.py tests/test_api_documents.py tests/test_api_jobs.py
git commit -m "feat: add FastAPI upload and job-status/streaming endpoints"
```

---

### Task 15: README and manual end-to-end verification

**Files:**
- Create: `README.md`

**Interfaces:** none (documentation + manual verification only).

- [ ] **Step 1: Write `README.md`**

```markdown
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
```

- [ ] **Step 2: Manually verify the golden path end-to-end**

```bash
uv run uvicorn app.main:app --reload &
sleep 2
curl -s -X POST http://localhost:8000/documents \
  -F "file=@tests/fixtures/manual_sample.txt;type=text/plain" \
  -F "doc_nature_hint=Mostly Text"
# copy the returned job_id, then:
curl -s http://localhost:8000/jobs/<job_id>
```

Create `tests/fixtures/manual_sample.txt` with a short paragraph beforehand if it
doesn't exist, e.g. an NCERT-style excerpt. Confirm the job reaches `status: completed`
(requires a valid `OPENROUTER_API_KEY` in `.env`) or `status: failed` with a clear
`error` message if no key is configured — either outcome confirms the pipeline wiring
is correct end-to-end. Stop the server afterward: `kill %1`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add Phase 1 README with setup and usage instructions"
```

---

## Self-Review Notes

- **Spec coverage:** Stage 1 (Tasks 5-9), Stage 2 (Task 11), Stage 3 (Task 12), streaming
  progress API (Task 14), grounding via `source_ref` (Task 2/12), cost-aware routing hint
  (Tasks 8/9), FAQ #4 no-hallucination framing (Task 12 prompt) — all covered.
- **Type consistency:** `route_and_parse`, `classify`, `extract`, `run_pipeline`,
  `JobManager.create_job/update_job/get_job`, `deps.job_manager` usage verified consistent
  across Tasks 9, 11, 12, 13, 14.
- **Deferred to Phase 2/3 (explicitly out of scope here):** teaching planner, content/
  activity/assessment generation, validation engine, TKP assembly, frontend UI, hosting/
  deployment.
