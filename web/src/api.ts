import { useEffect, useRef, useState } from "react";
import type { Event, RunView } from "./contracts";

export class ApiError extends Error {
  code: string; retryAfter: number | null;
  constructor(code: string, message: string, retryAfter: number | null = null) { super(message); this.code = code; this.retryAfter = retryAfter; }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { credentials: "same-origin", ...init });
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(body?.code ?? "NETWORK", body?.message ?? `Request failed (${r.status})`, body?.retry_after ?? null);
  return body as T;
}

const TERMINAL = new Set(["finished", "published", "awaiting_approval"]);

/** Polls the run + its events (contracts §3). Ignores responses older than what it already has. */
export function useRun(runId: string) {
  const [run, setRun] = useState<RunView | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const after = useRef(0);

  useEffect(() => {
    let stop = false, timer = 0;
    after.current = 0; setEvents([]); setRun(null); setError(null);
    const tick = async () => {
      try {
        const [r, e] = await Promise.all([
          api<RunView>(`/api/runs/${runId}`),
          api<{ events: Event[]; next_after: number }>(`/api/runs/${runId}/events?after=${after.current}`),
        ]);
        if (stop) return;
        const fresh = e.events.filter((x) => x.seq > after.current);   // stale-response guard
        if (fresh.length) { after.current = fresh[fresh.length - 1].seq; setEvents((p) => [...p, ...fresh]); }
        setRun(r); setError(null);
        if (!TERMINAL.has(r.status)) timer = window.setTimeout(tick, r.status === "paused" ? 10000 : 2000);
      } catch (err) {
        if (stop) return;
        setError(err as ApiError);
        if ((err as ApiError).code !== "NOT_FOUND") timer = window.setTimeout(tick, 5000);
      }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [runId]);

  return { run, events, error };
}
