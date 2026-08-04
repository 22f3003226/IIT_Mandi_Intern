import { useQuery } from "@tanstack/react-query";
import { getPublishResult, publishPdfUrl } from "../lib/api";

interface Tkp {
  classification: { subject: string; grade: string; topic: string; chapter: string };
  teaching_plan: { periods: Array<{ plan: { period_no: number; title: string; objectives: string[] } }> };
  validation_report: { passed: boolean; issues: Array<{ severity: string; description: string; location: string }> };
}

export function ResultStep({ publishJobId }: { publishJobId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["publish-result", publishJobId],
    queryFn: () => getPublishResult(publishJobId) as Promise<Tkp>,
  });

  if (isLoading) return <p className="text-neutral-400">Loading package...</p>;
  if (error) return <p className="text-red-400">Failed to load package.</p>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-medium">{data.classification.subject} — {data.classification.chapter}</h2>
        <p className="text-sm text-neutral-400">Grade {data.classification.grade} · {data.classification.topic}</p>
      </div>

      <div className={`rounded-md border px-4 py-3 text-sm ${data.validation_report.passed
        ? "border-emerald-900 bg-emerald-950/40 text-emerald-300"
        : "border-red-900 bg-red-950/40 text-red-300"}`}>
        Validation: {data.validation_report.passed ? "Passed" : "Issues found"}
        {data.validation_report.issues.length > 0 && (
          <ul className="mt-2 list-inside list-disc space-y-1">
            {data.validation_report.issues.map((issue, i) => (
              <li key={i}>[{issue.severity}] {issue.location}: {issue.description}</li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-neutral-300">Periods</h3>
        <ul className="space-y-2">
          {data.teaching_plan.periods.map((p) => (
            <li key={p.plan.period_no} className="rounded-md border border-neutral-800 p-3 text-sm">
              <p className="font-medium">Period {p.plan.period_no}: {p.plan.title}</p>
              <p className="text-neutral-400">{p.plan.objectives.join("; ")}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-wrap gap-3">
        {(["lesson-plan", "teacher-guide", "assessment-book"] as const).map((kind) => (
          <a key={kind} href={publishPdfUrl(publishJobId, kind)} target="_blank" rel="noreferrer"
             className="rounded-md border border-neutral-700 px-4 py-2.5 text-sm text-neutral-100 transition-colors hover:border-neutral-500 hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-100">
            Download {kind.replace("-", " ")}
          </a>
        ))}
      </div>
    </div>
  );
}
