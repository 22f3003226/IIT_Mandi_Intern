import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { createPlan, createPublish } from "./lib/api";
import { UploadStep } from "./components/UploadStep";
import { ProcessingStep } from "./components/ProcessingStep";
import { ResultStep } from "./components/ResultStep";
import { useJobStream } from "./hooks/useJobStream";

const queryClient = new QueryClient();

type Stage = "upload" | "parsing" | "planning" | "publishing" | "result" | "error";

const initialParams = new URLSearchParams(window.location.search);
const initialPublishJobId = initialParams.get("publish");
const initialDocumentJobId = initialPublishJobId ? null : initialParams.get("job");

function Wizard() {
  const [stage, setStage] = useState<Stage>(initialPublishJobId ? "publishing" : "upload");
  const [documentJobId, setDocumentJobId] = useState<string | null>(initialDocumentJobId);
  const [planJobId, setPlanJobId] = useState<string | null>(null);
  const [publishJobId, setPublishJobId] = useState<string | null>(initialPublishJobId);
  const [error, setError] = useState<string | null>(null);

  const documentEvent = useJobStream(stage === "parsing" ? documentJobId : null);
  const planEvent = useJobStream(stage === "planning" ? planJobId : null);

  useEffect(() => {
    if (documentJobId && stage === "upload") setStage("parsing");
  }, [documentJobId, stage]);

  useEffect(() => {
    if (stage === "parsing" && documentEvent?.status === "failed") {
      setError("Document parsing failed.");
      setStage("error");
    }
  }, [stage, documentEvent]);

  useEffect(() => {
    if (stage === "planning" && planEvent?.status === "failed") {
      setError("Plan generation failed.");
      setStage("error");
    }
  }, [stage, planEvent]);

  useEffect(() => {
    if (stage === "parsing" && documentEvent?.status === "completed" && documentJobId) {
      createPlan(documentJobId)
        .then((job) => {
          setPlanJobId(job.id);
          setStage("planning");
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Failed to start plan generation.");
          setStage("error");
        });
    }
  }, [stage, documentEvent, documentJobId]);

  useEffect(() => {
    if (stage === "planning" && planEvent?.status === "completed" && planJobId) {
      createPublish(planJobId)
        .then((job) => {
          setPublishJobId(job.id);
          window.history.replaceState(null, "", `?publish=${job.id}`);
          setStage("publishing");
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Failed to start publishing.");
          setStage("error");
        });
    }
  }, [stage, planEvent, planJobId]);

  const resetWizard = () => {
    setDocumentJobId(null);
    setPlanJobId(null);
    setPublishJobId(null);
    setError(null);
    window.history.replaceState(null, "", window.location.pathname);
    setStage("upload");
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      {stage === "upload" && <UploadStep onUploaded={setDocumentJobId} />}
      {stage === "parsing" && documentJobId && <ProcessingStep jobId={documentJobId} label="Analyzing document" />}
      {stage === "planning" && planJobId && <ProcessingStep jobId={planJobId} label="Building teaching plan" />}
      {stage === "publishing" && publishJobId && (
        <PublishGate
          publishJobId={publishJobId}
          onDone={() => setStage("result")}
          onError={(message) => {
            setError(message);
            setStage("error");
          }}
        />
      )}
      {stage === "result" && publishJobId && <ResultStep publishJobId={publishJobId} />}
      {stage === "error" && (
        <div className="rounded-lg border border-red-900 bg-red-950/40 p-8">
          <p className="mb-4 text-sm text-red-400">{error ?? "Something went wrong."}</p>
          <button
            type="button"
            onClick={resetWizard}
            className="rounded-md border border-neutral-700 px-4 py-2 text-sm text-neutral-100 hover:bg-neutral-800"
          >
            Back to upload
          </button>
        </div>
      )}
    </div>
  );
}

function PublishGate({
  publishJobId,
  onDone,
  onError,
}: {
  publishJobId: string;
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const event = useJobStream(publishJobId);
  useEffect(() => {
    if (event?.status === "completed") onDone();
    if (event?.status === "failed") onError("Validation or publishing failed.");
  }, [event, onDone, onError]);
  return <ProcessingStep jobId={publishJobId} label="Validating and packaging" />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-neutral-950 text-neutral-100">
        <header className="border-b border-neutral-800 px-6 py-4">
          <h1 className="text-lg font-medium tracking-tight">Teacher AI Platform</h1>
        </header>
        <main>
          <Wizard />
        </main>
      </div>
    </QueryClientProvider>
  );
}
