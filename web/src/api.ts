import { useEffect, useRef, useState } from "react";
import type { Event, RunView } from "./contracts";

export class ApiError extends Error {
  code: string; retryAfter: number | null;
  constructor(code: string, message: string, retryAfter: number | null = null) { super(message); this.code = code; this.retryAfter = retryAfter; }
}

/** Static showcase build (VITE_SHOWCASE=1, scripts/build_showcase.py): no backend, recorded JSON only. */
export const SHOWCASE = import.meta.env.VITE_SHOWCASE === "1";
const READ_ONLY = "This is a read-only showcase of recorded runs, so nothing runs or changes here. The live app runs on our demo machine.";
const slug = (s: string) => s.replace(/[^a-z0-9]+/gi, "_");

async function recorded<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const [p, q = ""] = path.split("?");
  if (p.endsWith("/events") && new URLSearchParams(q).get("after") !== "0")   // recorded events come all at once
    return { events: [], next_after: Number(new URLSearchParams(q).get("after")) } as T;
  let file = `/showcase${p}.json`;
  if (method === "POST" && (p === "/api/issues/check" || p === "/api/repos/explore"))
    file = `/showcase${p}/${slug(JSON.parse(String(init?.body ?? "{}")).url ?? "")}.json`;
  else if (method === "POST" && p === "/api/runs") file = "/showcase/api/runs/_started.json";   // "Start run" opens the recorded real run
  else if (method !== "GET") throw new ApiError("SHOWCASE", READ_ONLY);
  const r = await fetch(file);
  const body = r.ok ? await r.json().catch(() => null) : null;
  if (!body) throw p.startsWith("/api/runs/") ? new ApiError("NOT_FOUND", "This run isn't in the showcase.")
    : new ApiError("SHOWCASE", "The showcase only has recorded examples. Try tinycalc #1 from the home page.");
  if (body.__error) throw new ApiError(body.__error.code, body.__error.message);   // the backend's own answer, recorded
  return body as T;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (SHOWCASE) return recorded<T>(path, init);
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
