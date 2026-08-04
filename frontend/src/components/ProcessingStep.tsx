import { useJobStream } from "../hooks/useJobStream";

export function ProcessingStep({ jobId, label }: { jobId: string; label: string }) {
  const event = useJobStream(jobId);
  const progress = event?.progress ?? 0;
  const stage = event?.stage ?? "starting";
  const failed = event?.status === "failed";

  return (
    <div className="rounded-lg border border-neutral-800 p-8">
      <p className="mb-2 text-sm text-neutral-400">{label}: {failed ? "failed" : stage}</p>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-neutral-800"
        role="progressbar"
        aria-label={label}
        aria-valuenow={failed ? undefined : progress}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full transition-all ${failed ? "bg-red-500" : "bg-neutral-100"}`}
          style={{ width: `${failed ? 100 : progress}%` }}
        />
      </div>
      {failed && (
        <p className="mt-3 text-sm text-red-400">
          This step failed. Check the backend logs (a missing OPENROUTER_API_KEY is the usual cause).
        </p>
      )}
    </div>
  );
}
