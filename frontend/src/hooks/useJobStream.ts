import { useEffect, useState } from "react";
import { BASE_URL } from "../lib/api";

export interface JobStreamEvent {
  stage: string | null;
  progress: number;
  status: string;
}

export function useJobStream(jobId: string | null): JobStreamEvent | null {
  const [event, setEvent] = useState<JobStreamEvent | null>(null);

  useEffect(() => {
    setEvent(null);
    if (!jobId) return;
    const source = new EventSource(`${BASE_URL}/jobs/${jobId}/stream`);
    source.onmessage = (msg) => {
      const data = JSON.parse(msg.data) as JobStreamEvent;
      setEvent(data);
      if (data.status === "completed" || data.status === "failed") source.close();
    };
    return () => source.close();
  }, [jobId]);

  return event;
}
