import { useState } from "react";
import { api, ApiError } from "./api";
import type { RunView } from "./contracts";

type Answer = { question: string; answer: string; evidence_ids: string[] };
type Q = { question: "why_file" | "why_fails" | "why_fix"; path?: string; label: string };

/** S-03/S-04 Ask why: a few fixed questions, answered only from this run's evidence. Every answer shows its citations. */
export default function AskPanel({ run }: { run: RunView }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [err, setErr] = useState<{ q: Q; e: ApiError } | null>(null);
  const d = run.diagnosis;
  if (!run.repro || !/^[0-9a-f-]{36}$/.test(run.run_id)) return null;   // nothing to explain yet (or a sample run)
  const files = [...new Set([...(d?.locations ?? []).map((l) => l.path), ...(d?.tour ?? []).map((t) => t.path)])];
  const qs: Q[] = [
    ...files.map((p) => ({ question: "why_file" as const, path: p, label: `Why ${p}?` })),
    { question: "why_fails", label: "Why does the test fail?" },
    ...(run.patch ? [{ question: "why_fix" as const, label: "Why does this fix work?" }] : []),
  ];
  const ask = async (q: Q) => {
    setBusy(q.label); setErr(null);
    try {
      const a = await api<Answer>(`/api/runs/${run.run_id}/ask`, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: q.question, path: q.path ?? null }) });
      setAnswers((xs) => [a, ...xs]);
    } catch (e) {
      setErr({ q, e: e as ApiError });
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="card ask">
      <h2>Ask why</h2>
      <p className="hint">Answers come only from this run's evidence, and each one shows what it's based on.</p>
      <div className="ask-qs">
        {qs.map((q) => (
          <button key={q.label} className="secondary-btn" disabled={!!busy} onClick={() => ask(q)}>
            {busy === q.label ? "Thinking…" : q.label}
          </button>
        ))}
      </div>
      {err && (
        <div className="notice warn" role="alert">
          {err.e.message} <button className="linklike" onClick={() => ask(err.q)}>Try again</button>
        </div>
      )}
      {answers.map((a, i) => (
        <div key={i} className="answer">
          <p className="answer-q">{a.question}</p>
          <p>{a.answer}</p>
          <p className="hint">Based on: {a.evidence_ids.map((id, j) => (
            <a key={id} href={`/api/artifacts/${encodeURIComponent(id)}`}>{j ? ", " : ""}evidence {j + 1}</a>
          ))}</p>
        </div>
      ))}
    </div>
  );
}
