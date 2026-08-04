// Empty string means same-origin relative requests, which is correct in
// production (Docker serves the frontend and API from one origin). Local dev
// uses the Vite proxy (see vite.config.ts) to route these to :8000 instead.
export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export interface JobStatus {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string | null;
  progress: number;
  error: string | null;
  result_path: string | null;
}

// POST /documents (not /jobs) — confirmed from app/api/documents.py. It only
// returns {"job_id": string}, not a full JobStatus, so we normalize the shape
// here to keep the rest of the app working against the JobStatus interface.
export async function uploadDocument(file: File): Promise<JobStatus> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/documents`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  const data = (await res.json()) as { job_id: string };
  return { id: data.job_id, status: "queued", stage: null, progress: 0, error: null, result_path: null };
}

export async function createPlan(documentJobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE_URL}/jobs/${documentJobId}/plan`, { method: "POST" });
  if (!res.ok) throw new Error(`Plan creation failed: ${res.status}`);
  return res.json();
}

export async function createPublish(planJobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE_URL}/jobs/${planJobId}/publish`, { method: "POST" });
  if (!res.ok) throw new Error(`Publish creation failed: ${res.status}`);
  return res.json();
}

export async function getPublishResult(publishJobId: string): Promise<unknown> {
  const res = await fetch(`${BASE_URL}/jobs/${publishJobId}/publish`);
  if (!res.ok) throw new Error(`Fetching TKP failed: ${res.status}`);
  return res.json();
}

export function publishPdfUrl(publishJobId: string, kind: "lesson-plan" | "teacher-guide" | "assessment-book") {
  return `${BASE_URL}/jobs/${publishJobId}/publish/pdf/${kind}`;
}
