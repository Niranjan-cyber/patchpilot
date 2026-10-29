import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import type { RunView } from "./contracts";

const LABEL: Record<string, string> = { reproduce: "the failing test is written", diagnose: "the cause is found", fix: "the fix is written" };

/** B15 guided pauses: off by default; the run stops after a chosen step so a first-time contributor can look first. */
export function PauseToggles({ run }: { run: RunView }) {
  const [after, setAfter] = useState<string[] | null>(null);
  const [points, setPoints] = useState<string[]>([]);
  const [err, setErr] = useState<ApiError | null>(null);
  const real = /^[0-9a-f-]{36}$/.test(run.run_id);
  useEffect(() => {
    if (!real) return;
    api<{ after: string[]; points: string[] }>(`/api/runs/${run.run_id}/pauses`).then((p) => { setAfter(p.after); setPoints(p.points); })
      .catch(setErr);
  }, [run.run_id, real]);
  if (!real || run.outcome || after === null) return null;
  const toggle = (p: string) => {
    const next = after.includes(p) ? after.filter((x) => x !== p) : [...after, p];
    api<{ after: string[] }>(`/api/runs/${run.run_id}/pauses`, { method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify({ after: next }) }).then((r) => { setAfter(r.after); setErr(null); }).catch(setErr);
  };
  return (
    <fieldset className="card pauses">
      <legend>Pause so I can look</legend>
      {points.map((p) => (
        <label key={p}><input type="checkbox" checked={after.includes(p)} onChange={() => toggle(p)} /> after {LABEL[p] ?? p}</label>
      ))}
      <p className="hint">Off by default. Applies to steps that haven't started yet.</p>
      {err && <p className="notice warn">{err.message}</p>}
    </fieldset>
  );
}

/** Shown while the run waits for the user at a guided pause. */
export function GuidedPauseNotice({ run }: { run: RunView }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  if (run.status !== "paused" || run.pause?.reason !== "guided_pause") return null;
  const act = (path: string) => {
    setBusy(true); setErr(null);
    api(`/api/runs/${run.run_id}/${path}`, { method: "POST" }).catch(setErr).finally(() => setBusy(false));
  };
  return (
    <div className="notice guided" role="status">
      <strong>Paused so you can look.</strong> Read the steps and the likely cause, ask why, then continue when you're ready.
      <div className="guided-actions">
        <button disabled={busy} onClick={() => act("continue")}>{busy ? "Continuing…" : "Continue"}</button>
        <button className="danger-btn" disabled={busy} onClick={() => act("stop")}>Stop and keep the report</button>
      </div>
      {err && <p className="hint">{err.message}</p>}
    </div>
  );
}
