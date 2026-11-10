import { Fragment, type ReactNode } from "react";
import type { CheckStatus } from "./contracts";
import { Status, StatusIcon } from "./components";
import { anchor, parseDiff } from "./DiffView";
import { HV, NOCHECK, VREASON } from "./ExtraChecks";
import { CopyButton } from "./ui";

// #97: built by backend/api/approval.py explainer() from what the run recorded; statuses are never upgraded here
type Check = { id: "reproduced" | "fixed" | "baseline" | "hidden_variant" | "only_these_files" | "supplyguard" | "repo_check"; status: CheckStatus; tool?: string | null;
  note?: string | null; reason?: string | null; unsupported?: boolean; runs?: CheckStatus[]; regressions?: string[]; partial?: boolean | null;
  counts?: { passed: number; failed: number; flaky: number } | null; evidence?: string[] };
type Risk = { kind: "review"; severity?: string; text?: string; location?: string } | ({ kind: "check" } & Check)
  | { kind: "cap"; reason: string } | { kind: "uncovered"; text: string } | { kind: "coverage_not_checked" };
export type ExplainerData = {
  problem: { expected: string | null; actual: string | null; tests: string[]; failure: string | null; evidence: string[] };
  root_cause: { claim: string; evidence: string[]; citations: { path: string; line: number | null; url: string }[] } | null;
  fix: { only_these_files: CheckStatus; evidence: string[] };
  verification: Check[]; risks: Risk[]; readiness: string | null;
};

const CAP: Record<string, string> = {
  supplyguard_inconclusive: "We couldn't fully check the project's dependencies.",
  baseline_partial: "The existing tests only partly ran on the original code, so a break elsewhere could go unnoticed.",
  issue_unclear: "The issue doesn't say exactly what the right behaviour is, so our test is the only definition of correct.",
};

const label = (c: Check) => c.id === "repo_check" ? (c.tool ? `Repository check: ${c.tool}` : "The repository's own checks") : {
  reproduced: "The new test fails on the original code", fixed: "The new test passes with the fix",
  baseline: "Existing tests on the original code", hidden_variant: "Hidden test variant",
  only_these_files: "Only allowed files changed (no tests, dependencies or CI edited)", supplyguard: "Dependency check (SupplyGuard)" }[c.id];

// a reason we have no words for (e.g. "error: ValueError") is never shown raw
const why = (map: Record<string, string>, reason?: string | null) =>
  reason ? map[reason] ?? (reason.startsWith("error") ? "it stopped with an unexpected error" : "the reason wasn't recorded") : null;
const WORD: Record<string, string> = { passed: "Passed", failed: "Failed", inconclusive: "Inconclusive", not_run: "Not run", blocked: "Blocked" };
const word = (c: Check) => (c.unsupported ? "Unsupported" : WORD[c.status] ?? c.status);

const ofRuns = (runs: CheckStatus[] | undefined, want: CheckStatus) =>
  runs?.length ? `${runs.filter((r) => r === want).length} of ${runs.length} runs ${want === "failed" ? "failed" : "passed"}.` : "No runs recorded.";

function detail(c: Check): string {
  if ((c.id === "reproduced" || c.id === "fixed") && c.status === "not_run") return "Not run.";
  if (c.id === "reproduced") return ofRuns(c.runs, "failed");
  if (c.id === "fixed") return `${ofRuns(c.runs, "passed")} ${c.regressions?.length
    ? `${c.regressions.length} existing test${c.regressions.length === 1 ? "" : "s"} broke.` : "No existing test broke."}`;
  if (c.id === "baseline") return c.counts ? `${c.counts.passed} passed, ${c.counts.failed} failed, ${c.counts.flaky} flaky${c.partial ? " (only part of the suite ran)" : ""}.` : "No run recorded.";
  // passed / failed / inconclusive in the run page's own words; only "not run" takes a reason
  if (c.id === "hidden_variant") return c.status !== "not_run" && HV[c.status] ? HV[c.status][1]
    : `Not run${c.reason ? `: ${why(VREASON, c.reason)}` : ""}.`;
  if (c.id === "only_these_files" || c.id === "supplyguard") return "";
  if (c.tool) return c.note ?? "";
  return c.reason ? NOCHECK[c.reason] ?? `Not run: ${why(NOCHECK, c.reason)}.` : "Status unavailable.";
}

// one line per check, in the same words on screen and in the copied text
const line = (c: Check) => {
  const d = detail(c);
  return `${label(c)}: ${d.startsWith(word(c)) ? d : `${word(c)}.${d ? ` ${d}` : ""}`}`;   // never "Not run. Not run yet."
};

function riskText(r: Risk): ReactNode {
  if (r.kind === "review") return <>{r.text}{r.location && <> (<code>{r.location}</code>)</>}</>;
  if (r.kind === "check") return line(r);
  if (r.kind === "cap") return CAP[r.reason] ?? r.reason;
  if (r.kind === "uncovered") return <>The test doesn't check: {r.text}</>;
  return "We didn't check whether the test covers everything the issue expects.";
}

const Evidence = ({ ids }: { ids: string[] }) => ids.length ? (
  <p className="hint">Recorded evidence: {ids.map((id, j) => (
    <a key={`${j}-${id}`} href={`/api/artifacts/${encodeURIComponent(id)}`}>{j ? ", " : ""}evidence {j + 1}</a>))}</p>) : null;

function Part({ title, copy, children }: { title: string; copy?: [string, string]; children: ReactNode }) {
  return (
    <details className="explainer-part">
      <summary>{title}</summary>
      <div className="explainer-body">
        {children}
        {copy && <p className="explainer-copy"><CopyButton text={copy[1]} label={copy[0]} /> Copy the {copy[0].toLowerCase()}</p>}
      </div>
    </details>
  );
}

/** #98: the recorded evidence for one ownership question, from the explainer payload (no second copy of the logic). */
export function QuestionEvidence({ q, e, fixFiles, diff }: { q: string; e: ExplainerData; fixFiles: string[]; diff: string }) {
  const p = e.problem;
  if (q === "what_was_broken") return (
    <dl className="explainer-kv question-evidence">
      <dt>Expected</dt><dd>{p.expected ?? "The issue doesn't say."}</dd>
      <dt>Actual</dt><dd>{p.actual ?? "The issue doesn't say."}</dd>
      <dt>Test failure</dt><dd>{p.failure ? <code>{p.failure}</code> : "No failure was recorded."}</dd>
    </dl>
  );
  if (q === "why_this_fix") {
    const changed = parseDiff(diff).filter((f) => fixFiles.includes(f.path));
    return (
      <dl className="explainer-kv question-evidence">
        <dt>Cause</dt><dd>{e.root_cause ? <>{e.root_cause.claim} <span className="text-muted">(PatchPilot's claim)</span></> : "Unknown: no diagnosis was recorded."}</dd>
        <dt>Changed</dt><dd>{changed.length ? changed.map((f, i) => (
          <span key={`${i}-${f.path}`} className="question-file"><a href={`#${anchor(f.path)}`}><code>{f.path}</code></a>{" "}
            <span className="count"><span className="add">+{f.adds}</span> <span className="del">−{f.dels}</span></span></span>)) : "No source file changed."}</dd>
      </dl>
    );
  }
  const runs = e.verification.filter((c) => c.id === "reproduced" || c.id === "fixed");
  return (
    <dl className="explainer-kv question-evidence">
      <dt>Test</dt><dd>{p.tests.length ? p.tests.map((t, i) => <code key={`${i}-${t}`}>{t}</code>) : "No test was recorded."}</dd>
      {runs.map((c) => <Fragment key={c.id}><dt>{c.id === "reproduced" ? "Original code" : "With the fix"}</dt>
        <dd><Status s={c.status} /> {detail(c)}</dd></Fragment>)}
    </dl>
  );
}

/** The Review screen's Contribution Explainer: five sections, each collapsed and readable on its own. */
export default function Explainer({ e, diff }: { e: ExplainerData; diff: string }) {
  const files = parseDiff(diff);
  const tests = e.verification.filter((c) => c.id === "reproduced" || c.id === "fixed");
  return (
    <details className="explainer">
      <summary>Not sure? How PatchPilot reached this change</summary>
      <p className="hint">Read the change with this in mind, then answer the questions in your own words.</p>

      <Part title="Problem" copy={["Test evidence", [...e.problem.tests, e.problem.failure && `Fails on the original code with: ${e.problem.failure}`,
        ...tests.map(line)].filter(Boolean).join("\n")]}>
        <dl className="explainer-kv">
          <dt>Expected</dt><dd>{e.problem.expected ?? "The issue doesn't say."}</dd>
          <dt>Actual</dt><dd>{e.problem.actual ?? "The issue doesn't say."}</dd>
          <dt>Reproduced by</dt><dd>{e.problem.tests.length ? e.problem.tests.map((t) => <code key={t}>{t}</code>) : "No test recorded."}
            {e.problem.failure && <> fails on the original code with <code>{e.problem.failure}</code></>}</dd>
        </dl>
        <Evidence ids={e.problem.evidence} />
      </Part>

      <Part title="Root cause" copy={e.root_cause ? ["Root cause", [e.root_cause.claim,
        ...e.root_cause.citations.map((c) => c.url)].join("\n")] : undefined}>
        {e.root_cause ? <>
          <p><strong>PatchPilot's diagnosis (a claim):</strong> {e.root_cause.claim}</p>
          {e.root_cause.citations.length > 0 && <ul className="explainer-list">{e.root_cause.citations.map((c, i) => (
            <li key={`${i}-${c.url}`}><a href={c.url} target="_blank" rel="noreferrer"><code>{c.path}{c.line ? `:${c.line}` : ""}</code></a> at the tested commit</li>))}</ul>}
          <Evidence ids={e.root_cause.evidence} />
        </> : <p>No diagnosis was recorded for this run.</p>}
      </Part>

      <Part title="Fix" copy={["Fix summary", [...files.map((f) => `${f.path} (+${f.adds} −${f.dels})`),
        `Only these files changed: ${WORD[e.fix.only_these_files] ?? e.fix.only_these_files}.`].join("\n")]}>
        <ul className="explainer-list">{files.map((f) => (
          <li key={f.path}><a href={`#${anchor(f.path)}`}><code>{f.path}</code></a> <span className="count"><span className="add">+{f.adds}</span> <span className="del">−{f.dels}</span></span></li>))}</ul>
        <p><Status s={e.fix.only_these_files} /> Only these files changed</p>
        <Evidence ids={e.fix.evidence} />
      </Part>

      <Part title="Verification">
        <ul className="explainer-list">{e.verification.map((c, i) => (
          <li key={i}>{c.unsupported ? <span className="status status-not_run"><StatusIcon s="not_run" size={12} />Unsupported</span> : <Status s={c.status} />}{" "}
            <strong>{label(c)}</strong>{detail(c) && <>: {detail(c)}</>}{c.evidence && <Evidence ids={c.evidence} />}</li>))}</ul>
      </Part>

      <Part title={`Remaining risks (${e.risks.length})`}>
        {e.readiness && <p>Readiness: <strong>{e.readiness}</strong></p>}
        {e.risks.length ? <ul className="explainer-list">{e.risks.map((r, i) => <li key={i}>{riskText(r)}</li>)}</ul>
          : <p>No open risks were recorded for this run.</p>}
      </Part>
    </details>
  );
}
