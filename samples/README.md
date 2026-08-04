# Sample outputs

Two sample runs of the full pipeline (parse, classify, extract, plan,
generate, validate, publish), each against a real OpenRouter call at
every LLM-calling stage. No fixtures, no fabricated data.

- `physics/`: a Newton's Laws of Motion chapter (STEM). The validator
  caught a real issue here: the generated teaching plan proposed a
  demonstration using "small ramps" that weren't mentioned anywhere in
  the extracted knowledge, so `validation_report.passed` is `false` with
  one `critical`/`hallucination` issue on period 2. The job still
  completed with a full package and all three PDFs, exactly as
  designed: validation failures are surfaced, not swallowed, and they
  never block publishing.
- `history/`: a French Revolution chapter (Humanities). Clean pass, no
  validation issues.

Each folder has `TeacherKnowledgePackage.json` plus the three generated
PDFs (`lesson-plan.pdf`, `teacher-guide.pdf`, `assessment-book.pdf`).

To generate more, set `OPENROUTER_API_KEY` in `.env` and run:

```python
from app_gradio import run_pipeline

class Progress:
    def __call__(self, frac, desc=""):
        print(f"[{frac:.2f}] {desc}")

summary, tkp_path, lesson_pdf, guide_pdf, assessment_pdf = run_pipeline(
    "path/to/your/document.pdf", "Not Sure", Progress()
)
```

or use the frontend wizard (`npm run dev` in `frontend/`) against a
locally running backend, and copy the completed publish job's output
from `storage/files/{publish_job_id}/`.
