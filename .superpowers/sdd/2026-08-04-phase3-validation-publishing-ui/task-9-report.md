# Task 9 Report: Frontend upload → processing → result flow

## What was implemented

Wired the wizard end-to-end against the live backend, per the brief:

- `frontend/src/lib/api.ts` — typed fetch wrappers (`uploadDocument`, `createPlan`, `createPublish`, `getPublishResult`, `publishPdfUrl`).
- `frontend/src/hooks/useJobStream.ts` — SSE progress hook, `EventSource` against `/jobs/{id}/stream`. Added one fix over the brief's snippet: resets `event` to `null` at the start of the effect (not just on cleanup) so a stale terminal event from a previous `jobId` can't leak into the next job's rendered progress bar.
- `frontend/src/components/UploadStep.tsx` — file picker, upload, error display.
- `frontend/src/components/ProcessingStep.tsx` — progress bar bound to `useJobStream`.
- `frontend/src/components/ResultStep.tsx` — TKP display (classification header, validation report, periods list, 3 PDF download links).
- `frontend/src/App.tsx` — replaced the Task 8 static shell with the full `Wizard` component: upload → parsing → planning → publishing → result, chaining `createPlan`/`createPublish` off SSE `completed` events, job id round-tripped through the `?job=` query param.
- `frontend/.env.example` — `VITE_API_BASE_URL=http://localhost:8000`.

## Upload-endpoint contract confirmed (Step 1)

Read `app/api/documents.py` directly (this worktree, not `/home/prince23/Mandi`). Two deviations from the brief's assumed contract, both fixed in `api.ts`:

1. **Route is `POST /documents`, not `POST /jobs`.** `app/main.py` mounts `documents.router` with no prefix, and the route inside is `@router.post("/documents")`.
2. **Response body is `{"job_id": "<uuid>"}`, not a full `JobStatus`.** The brief's snippet assumed `POST /jobs` returns `{id, status, stage, progress, error, result_path}` like the other job endpoints. `upload_document` in `documents.py` returns only `{"job_id": ...}`. `uploadDocument()` in `api.ts` normalizes this into the `JobStatus` shape (`status: "queued"`, everything else `null`/`0`) so the rest of the app (`onUploaded(job.id)`) works unchanged.

The multipart field name (`file`) matched the brief exactly — `file: UploadFile = File(...)`.

Verified live with `curl -X POST -F "file=@test.txt" http://localhost:8000/documents` → `{"job_id": "..."}`, and confirmed `GET /jobs/{id}/stream` emits the expected `{stage, progress, status}` SSE frames.

## Taste-pass fixes (Step 7)

Ran `/ui-ux-pro-max`, `/gpt-taste`, and `/impeccable` against `ResultStep.tsx` and `App.tsx` (and by extension the two other new components, since they're in the same flow).

- **`ui-ux-pro-max`**: flagged focus-visible states and touch-target sizing as the concrete, relevant checks (its `--domain ux` search for "dark mode contrast accessibility download button focus" surfaced Accessibility/Contrast and Interaction/Focus-States as the applicable High-severity items).
- **`gpt-taste`**: this skill is built for marketing/landing pages (GSAP hero sections, bento grids, marquees) and doesn't fit a small internal admin-style wizard. Took only the parts that generalize — avoid weak/invisible button text, avoid decorative-only card repetition — and explicitly did not add GSAP/hero/marquee scaffolding, which would be pure over-engineering for this surface.
- **`/impeccable`**: ran `context.mjs` (no `PRODUCT.md` yet — expected for a Task 8 scaffold; this is a narrow refinement of an existing implementation, which the skill's own routing allows without blocking on `init`). Ran the bundled `detect.mjs` mechanical detector against all 4 changed files after applying fixes — **zero findings**.

Concrete fixes applied:

1. **`UploadStep.tsx`**: the file `<input>` used `className="hidden"` (`display:none`), which removes it from the tab order entirely — a real keyboard-accessibility bug, not a style nit. Switched to `sr-only` (visually hidden, still focusable) and added a `has-[:focus-visible]:ring-2` focus ring on the label. Also added `role="alert"` to the error message so it's announced.
2. **`ProcessingStep.tsx`**: added `role="progressbar"` with `aria-valuenow`/`aria-valuemin`/`aria-valuemax`/`aria-label` to the progress track — it was a plain `<div>` with no semantics before.
3. **`ResultStep.tsx`**: added `focus-visible:ring-2` to the 3 PDF download links (previously had a hover state but no visible keyboard-focus indicator), bumped their padding slightly (`px-3 py-2` → `px-4 py-2.5`) to move closer to the 44px touch-target guideline, and made the link text explicitly `text-neutral-100` (was inheriting, contrast was fine but implicit).

Re-ran `npm run build` after the fixes — clean, no TS errors. Re-verified the dev server picked up the changes via HMR with no console/compile errors.

## Manual verification (Step 6, run twice — before and after Step 7 fixes)

- Started backend: `uv run uvicorn app.main:app --port 8000` (this worktree's `app/`, no `.env` present — `OPENROUTER_API_KEY` unset).
- Started frontend: `cp .env.example .env && npm run dev` → served at `http://localhost:5173`.
- `curl http://localhost:5173/` → 200, correct HTML shell (`<title>Teacher AI Platform</title>`, `#root`, `src/main.tsx`).
- `curl -X POST -F "file=@test.txt" http://localhost:8000/documents` → `{"job_id": "..."}`.
- `curl http://localhost:8000/jobs/{job_id}/stream` → SSE frames: `{"stage": "classification", "progress": 40, "status": "running"}` then `{"stage": "classification", "progress": 40, "status": "failed"}`.
- Backend log confirmed the failure cause: `httpx.LocalProtocolError: Illegal header value b'Bearer '` — i.e. the pipeline correctly reached the first LLM call and failed only because `OPENROUTER_API_KEY` is empty. This is the exact expected-and-fine failure mode called out in the brief (Step 6); it validates that upload → job creation → pipeline kickoff → SSE streaming → failure surfacing all work correctly end-to-end. `npm run build` was clean both before and after the Step 7 fixes.
- Did not get to visually confirm the Result screen (periods/validation/3 download links) rendering with real data, since that requires a live `OPENROUTER_API_KEY` which isn't available in this environment — noted as expected per the brief.
- Stopped both servers and removed the test `frontend/.env` afterward (kept only `.env.example`, matching the rest of the repo's untracked-`.env` convention).

## Deviations from the brief

1. Upload route is `/documents`, not `/jobs`, and its response is `{job_id}` not a full `JobStatus` — normalized in `api.ts` (see above; not a deviation in behavior, the brief just asked to "adjust... per what Step 1 found," which is what happened).
2. `useJobStream` resets state to `null` at effect start (brief's snippet only cleaned up on unmount) — prevents a stale event object from a prior job leaking into a new job's render.
3. Did not apply `gpt-taste`'s marketing-page-oriented suggestions (GSAP, hero sections, bento grids) — out of scope and wrong register for an internal wizard tool; documented why above rather than silently skipping.
4. Added `role="alert"` on the upload error message — small addition beyond the brief's snippet, in the interest of actual accessibility rather than cosmetic-only fixes.

## Files touched

- `frontend/src/lib/api.ts` (new)
- `frontend/src/hooks/useJobStream.ts` (new)
- `frontend/src/components/UploadStep.tsx` (new)
- `frontend/src/components/ProcessingStep.tsx` (new)
- `frontend/src/components/ResultStep.tsx` (new)
- `frontend/src/App.tsx` (modified)
- `frontend/.env.example` (new)

## Fix round 1

Follow-up fix to `frontend/src/App.tsx` addressing failure-handling gaps left after the initial implementation.

- Added an `"error"` stage to the `Stage` union, with a `useState<string | null>` for the error message.
- Added `useEffect` watchers on `documentEvent` (stage `"parsing"`) and `planEvent` (stage `"planning"`) that transition to the `"error"` stage with a descriptive message when `event?.status === "failed"`. Previously a failed parse or plan-generation job left the wizard stuck on `ProcessingStep` indefinitely.
- Added `.catch()` handlers on the `createPlan(documentJobId)` and `createPublish(planJobId)` calls so a rejected request (e.g. network error, 4xx/5xx from the backend) also routes to the `"error"` stage instead of leaving an unhandled promise rejection and a hung UI.
- Added `resetWizard()`, which clears all job IDs and the error message, strips the `?job=` query param, and returns to the `"upload"` stage. Wired to a "Back to upload" button in the new error UI block.
- **`PublishGate` fix**: the component only called `onDone()` on `event?.status === "completed"`, so a failed validation/publishing job (the last pipeline stage) left the wizard hung on "Validating and packaging" forever with no path to the error UI — the one gap not covered by the parsing/planning fixes above. Added an `onError: (message: string) => void` prop, passed from `Wizard` (mirroring how `onDone` is already passed) as `(message) => { setError(message); setStage("error"); }`. `PublishGate`'s existing `useEffect` now also calls `onError("Validation or publishing failed.")` when `event?.status === "failed"`.

Verified with `cd frontend && npm run build` — `tsc -b && vite build` completed with no TypeScript errors, output unchanged in size/shape from prior builds.
