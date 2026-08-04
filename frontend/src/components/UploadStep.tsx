import { useState } from "react";
import { uploadDocument } from "../lib/api";

export function UploadStep({ onUploaded }: { onUploaded: (jobId: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const job = await uploadDocument(file);
      onUploaded(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 p-8 text-center">
      <label className="inline-flex cursor-pointer rounded-md px-2 py-1 text-sm text-neutral-300 has-[:focus-visible]:outline-none has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-neutral-100">
        {busy ? "Uploading..." : "Choose a PDF, DOCX, PPTX, or TXT file"}
        <input type="file" className="sr-only" onChange={handleChange} disabled={busy}
               accept=".pdf,.docx,.pptx,.txt" />
      </label>
      {error && <p className="mt-2 text-sm text-red-400" role="alert">{error}</p>}
    </div>
  );
}
