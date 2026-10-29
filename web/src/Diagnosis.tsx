import type { Event, RunView } from "./contracts";

const blob = (run: RunView, path: string, line?: number | null) =>
  `https://github.com/${run.issue.repo}/blob/${run.base_sha}/${path}${line ? `#L${line}` : ""}`;
const ev = (id: string) => `/api/artifacts/${encodeURIComponent(id)}`;

const ROLE: Record<string, string> = { test_designer: "Test writer", investigator: "Investigator", fixer: "Fixer" };
const REASON: Record<string, string> = {
  edits_tests: "changed a test file (fixes may only change source code)",
  dependency_change: "changed a dependency file", ci_change: "changed .github/",
  too_many_files: "changed more than 5 files", too_many_lines: "changed more than 200 lines",
  empty_diff: "didn't change anything", binary_change: "changed a binary file", no_fix_written: "didn't finish a fix",
  unknown_evidence_id: "cited evidence that doesn't exist", unknown_file: "pointed to a file that doesn't exist",
  line_out_of_range: "pointed past the end of a file", no_location: "didn't point to any code",
  no_evidence: "didn't cite any evidence", no_hypothesis: "didn't explain the cause", no_result: "didn't finish",
  no_test_written: "didn't finish a test",
};

/** S-03 "Likely cause": every location and tour file links to the pinned commit, so a first-time contributor can read along. */
export function DiagnosisCard({ run }: { run: RunView }) {
  const d = run.diagnosis;
  if (!d) {
    if (run.steps?.diagnose?.status !== "failed") return null;
    return (
      <div className="card">
        <h2>Likely cause</h2>
        <p className="hint">Diagnosis unavailable: we couldn't back up a cause with evidence we could check. The failing test is still in the report.</p>
      </div>
    );
  }
  return (
    <div className="card diagnosis">
      <h2>Likely cause <span className="sample" title="Written by AI, checked against real files and evidence">Estimate</span></h2>
      <p>{d.hypothesis}</p>
      <ul className="locs">
        {(d.locations ?? []).map((l) => (
          <li key={`${l.path}:${l.line}`}><a href={blob(run, l.path, l.line)}><code>{l.path}{l.line ? `:${l.line}` : ""}</code></a></li>
        ))}
      </ul>
      {!!d.tour?.length && (
        <>
          <h3>Codebase tour</h3>
          <ol className="tour">{d.tour.map((t) => <li key={t.path}><a href={blob(run, t.path)}><code>{t.path}</code></a> {t.why}</li>)}</ol>
        </>
      )}
      {!!d.evidence_ids?.length && (
        <p className="hint">Evidence: {d.evidence_ids.map((id, i) => <a key={id} href={ev(id)}>{i ? ", " : ""}#{i + 1}</a>)}</p>
      )}
    </div>
  );
}

/** "Show details": every rejected attempt, who made it, and the rule it broke. Rejections count as attempts. */
export function AttemptHistory({ events }: { events: Event[] }) {
  const tries = events.filter((e) => e.type === "attempt.retry");
  if (!tries.length) return null;
  return (
    <details className="card attempts">
      <summary>Show details ({tries.length} rejected attempt{tries.length > 1 ? "s" : ""})</summary>
      <ol>
        {tries.map((e) => {
          const p = (e.payload ?? {}) as { role?: string; attempt?: number; max?: number; reason?: string; evidence_ids?: string[] };
          return (
            <li key={e.seq}>
              <strong>{ROLE[p.role ?? ""] ?? p.role} attempt {p.attempt} of {p.max}</strong>: rejected because it{" "}
              {REASON[p.reason ?? ""] ?? p.reason}.
              {p.evidence_ids?.map((id, i) => <span key={id}> <a href={ev(id)}>{i ? "diff" : "transcript"}</a></span>)}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
