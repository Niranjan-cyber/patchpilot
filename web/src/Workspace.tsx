import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import type { Event, RunView } from "./contracts";
import { Icon, Status, StatusIcon, STEPS } from "./components";
import { CopyButton, Drawer } from "./ui";

type Step = { status?: string; headline?: string | null; started_at?: string | null; finished_at?: string | null; attempt?: number };
const GATE: Record<string, [string, string]> = {
  preflight: ["G1", "Dependency check: blocks known-malicious or typosquatted packages before anything installs."],
  setup: ["G2", "The project installs in an isolated sandbox and its tests can be collected."],
  reproduce: ["G3", "The new test fails on the original code, twice, for the reason the issue describes."],
  fix: ["G4", "The diff only touches source files: no tests, CI or packaging edited."],
  verify: ["G5", "In a fresh sandbox the new test passes twice and every test that passed before still passes."],
  review: ["G6", "The report is written by code from the recorded gates, not by the AI."],
};
const time = (s?: string | null) => (s ? new Date(s).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : null);
const took = (a?: string | null, b?: string | null) => {
  if (!a || !b) return null;
  const s = Math.max(0, Math.round((+new Date(b) - +new Date(a)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
};

/** What this stage recorded, from the run itself. Nothing is shown that the backend didn't record. */
function StageEvidence({ id, run }: { id: string; run: RunView }) {
  const r = run as RunView & Record<string, any>;
  switch (id) {
    case "preflight": return r.supplyguard ? <p>Dependency report: <Status s={r.supplyguard.status} /></p> : <p className="hint">No dependency report recorded.</p>;
    case "setup": return r.env ? (
      <dl className="kv">
        <dt>Python</dt><dd><span>{r.env.python_version}</span></dd>
        <dt>Tests run with</dt><dd><code>{r.env.test_cmd}</code><CopyButton text={String(r.env.test_cmd ?? "")} label="Command" /></dd>
      </dl>) : <p className="hint">No environment recorded for this run.</p>;
    case "baseline": return r.baseline ? (
      <dl className="kv">
        <dt>Passing before</dt><dd><span>{r.baseline.pass_set?.length ?? 0} tests</span></dd>
        <dt>Already failing</dt><dd><span>{r.baseline.fail_set?.length ?? 0} tests (not caused by this change)</span></dd>
        {!!r.baseline.flaky_set?.length && <><dt>Flaky</dt><dd><span>{r.baseline.flaky_set.length}</span></dd></>}
      </dl>) : <p className="hint">Not run.</p>;
    case "reproduce": return r.repro ? (
      <>
        <dl className="kv">{r.repro.test_ids.map((t: string) => <Fragment key={t}><dt>Test</dt><dd><code>{t}</code><CopyButton text={t} label="Test id" /></dd></Fragment>)}</dl>
        {r.repro.expected_failure && <div><span className="hint">Failure on the original code</span><pre className="term">{r.repro.expected_failure}</pre></div>}
      </>) : <p className="hint">No reproduction recorded.</p>;
    case "diagnose": return r.diagnosis ? (
      <>
        <p>{r.diagnosis.hypothesis} <span className="sample" data-tip="Written by the AI and checked against cited evidence. It can still be wrong.">AI estimate</span></p>
        {!!r.diagnosis.locations?.length && <ul>{r.diagnosis.locations.map((l: { path: string; line?: number | null }) => <li key={l.path + l.line}><code>{l.path}{l.line ? `:${l.line}` : ""}</code></li>)}</ul>}
      </>) : <p className="hint">No diagnosis recorded.</p>;
    case "fix": return r.patch ? (
      <p>Policy check: <Status s={r.patch.policy_result} /> · attempt {r.patch.attempt} · <Link to={`/runs/${run.run_id}/review`}>Read the change</Link></p>
    ) : <p className="hint">No fix recorded.</p>;
    case "verify": return r.verify ? (
      <dl className="kv">
        <dt>New test, fresh sandbox</dt><dd><span>{(r.verify.new_test_runs ?? []).map((s: string, i: number) => <Status key={i} s={s as never} />)}</span></dd>
        <dt>Regressions</dt><dd><span>{r.verify.regressions?.length ? r.verify.regressions.join(", ") : "None"}</span></dd>
      </dl>) : <p className="hint">Not verified.</p>;
    case "review": return r.review ? <p>{r.review.concerns?.length ? `${r.review.concerns.length} concern${r.review.concerns.length === 1 ? "" : "s"}, listed under Review findings.` : "The reviewer raised no concerns."}</p> : <p className="hint">The reviewer hasn't run.</p>;
  }
  return null;
}

export function StageNavigator({ run }: { run: RunView }) {
  const steps = (run.steps ?? {}) as Record<string, Step>;
  const focus = STEPS.find((s) => ["running", "failed", "blocked"].includes(steps[s.id]?.status ?? ""))?.id;
  const [open, setOpen] = useState<Record<string, boolean>>(focus ? { [focus]: true } : {});
  const gates = (run.gates ?? {}) as Record<string, string>;
  return (
    <ol className="stages list-none p-3 md:p-4 bg-white rounded-[var(--radius-card)]" aria-label="What PatchPilot did">
      {STEPS.map((st, n) => {
        const s = steps[st.id] ?? {};
        const k = s.status ?? "not_run";
        const isOpen = !!open[st.id];
        const g = GATE[st.id];
        const node = k === "passed" ? "bg-mint-500 text-white" : k === "failed" || k === "blocked" ? "bg-rose-500 text-white"
          : k === "running" ? "bg-lav-500 text-white" : k === "inconclusive" ? "bg-butter-300 text-ink" : "bg-soft text-faint";
        return (
          <motion.li key={st.id} className={`stage s-${k}${isOpen ? " open" : ""} relative rounded-[20px] transition-colors ${isOpen ? "bg-ground" : "hover:bg-ground/70"}`}
            aria-current={k === "running" ? "step" : undefined}
            initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 + n * 0.05, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}>
            {n < STEPS.length - 1 && <span aria-hidden className={`absolute left-[29px] top-[44px] -bottom-[12px] w-0.5 rounded ${k === "passed" ? "bg-mint-300" : "bg-line"}`} />}
            <button className="stage-btn !bg-transparent hover:!bg-transparent !transform-none w-full !justify-start !whitespace-normal text-left !min-h-[60px] !px-3 !gap-4 !font-normal"
              aria-expanded={isOpen} aria-controls={`stage-${st.id}`} onClick={() => setOpen({ ...open, [st.id]: !isOpen })}>
              <span className={`stage-node relative z-[1] grid place-items-center shrink-0 w-9 h-9 rounded-full ${node} ${k === "running" ? "animate-pulse" : ""}`}><StatusIcon s={k} size={16} /></span>
              <span className="stage-title flex-1 min-w-0 flex flex-col md:flex-row md:items-baseline gap-x-3 gap-y-0.5">
                <strong className="font-semibold text-[15px] shrink-0">{st.label}</strong>
                {s.headline && <span className="stage-line text-muted text-[14px]">{s.headline}</span>}
              </span>
              <span className="stage-time text-faint text-[12.5px] hidden sm:inline">{(t => t === "0s" ? "" : t)(took(s.started_at, s.finished_at) ?? "")}</span>
              {k === "passed" ? <span className="sr-only">Passed</span> : <Status s={k as never} />}
              <span className={`chev text-faint transition-transform duration-300 ${isOpen ? "rotate-90" : ""}`}><Icon name="chev" size={14} /></span>
            </button>
            <div className="reveal" id={`stage-${st.id}`}><div>
              <div className="stage-detail pl-[68px] pr-4 pb-5 grid gap-3 text-[14px]">
                                <dl className="kv">
                  <dt>Started</dt><dd><span>{time(s.started_at) ?? "—"}</span></dd>
                  <dt>Finished</dt><dd><span>{time(s.finished_at) ?? "—"}</span></dd>
                  {s.attempt ? <><dt>Attempt</dt><dd><span>{s.attempt}</span></dd></> : null}
                  {g && <><dt><span data-tip={g[1]} tabIndex={0}>Gate {g[0]}</span></dt><dd><Status s={(gates[g[0]] ?? "not_run") as never} /></dd></>}
                </dl>
                {k !== "not_run" && <StageEvidence id={st.id} run={run} />}
              </div>
            </div></div>
          </motion.li>
        );
      })}
    </ol>
  );
}

const SEV: Record<string, string> = { high: "High concern", medium: "Medium concern", low: "Low concern" };
// #70 item 9: the Reviewer's level; older runs only have a severity
const LEVEL: Record<string, string> = { BLOCKER: "Blocker", IMPORTANT: "Important", SUGGESTION: "Suggestion", ACCEPTED_TRADEOFF: "Accepted trade-off" };
type Finding = { severity?: string; level?: string; text?: string; dimension?: string; location?: string; action?: string; evidence?: string };
/** The independent reviewer's concerns. Blockers and important ones lower readiness (contracts §1.1 G6); none is a pass by itself. */
export function Findings({ run }: { run: RunView }) {
  const review = run.review as { concerns?: Finding[] } | null | undefined;
  const reviewStep = (run.steps as Record<string, Step> | undefined)?.review?.status;
  return (
    <section aria-labelledby="findings-h">
      <div className="section-head"><h2 id="findings-h"><Icon name="eye" />Review findings</h2>
        <span className="hint">An independent AI reviewer reads the diff. It can only lower readiness, never raise it.</span></div>
      {!review ? <p className="lane-empty">{reviewStep === "running" ? "The reviewer is reading the change."
          : !reviewStep || reviewStep === "not_run" ? "The reviewer hasn't run on this change." : "No reviewer findings were recorded for this run."}</p>
        : !review.concerns?.length ? <p className="lane-empty">The reviewer raised no concerns. That isn't proof the change is right; read the diff.</p>
        : <div className="findings">{review.concerns.map((c, i) => (
          <div key={i} className={`finding sev-${c.severity ?? "low"}`}><div>
            <div className="finding-head"><span className="sev">{LEVEL[c.level ?? ""] ?? SEV[c.severity ?? ""] ?? "Concern"}</span>
              {c.dimension && <span className="hint">{c.dimension.replaceAll("_", " ")}</span>}{c.location && <code>{c.location}</code>}</div>
            <p>{c.text}</p>
            {c.action && <p><strong>To do:</strong> {c.action}</p>}
            {c.evidence && <p className="hint">Evidence: <code>{c.evidence}</code></p>}
          </div></div>))}</div>}
    </section>
  );
}

const EV_WORD: Record<string, string> = {
  "run.queued": "Queued", "run.started": "Started", "run.resumed": "Resumed", "run.interrupted": "Interrupted", "run.paused": "Paused",
  "run.finished": "Finished", "step.started": "Step started", "step.finished": "Step finished", "step.progress": "Progress",
  "attempt.retry": "Retry", "analysis.finished": "Assessment finished",
};
export function ActivityButton({ events }: { events: Event[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="secondary" onClick={() => setOpen(true)}><Icon name="activity" />Activity log<span className="hint">{events.length}</span></button>
      <Drawer open={open} onClose={() => setOpen(false)} title="Activity log">
        <p className="hint">Every event this run recorded, oldest first.</p>
        {events.length ? (
          <ol className="log">{events.map((e) => {
            const p = (e.payload ?? {}) as Record<string, unknown>;
            const st = String(p.status ?? "");
            const cls = st === "passed" ? "ev-pass" : st === "failed" || st === "blocked" ? "ev-fail" : e.type === "step.started" ? "ev-run" : "";
            return (
              <li key={e.seq} className={cls}>
                <time dateTime={e.ts}>{new Date(e.ts).toLocaleTimeString()}</time>
                {EV_WORD[e.type] ?? e.type}{e.step ? <> · <strong>{STEPS.find((s) => s.id === e.step)?.label ?? e.step}</strong></> : null}
                {(() => { const note = p.headline ?? p.message ?? p.reason; return note ? <div className="hint">{String(note)}</div> : null; })()}
              </li>);
          })}</ol>
        ) : <p className="lane-empty">No events yet.</p>}
      </Drawer>
    </>
  );
}

/** Real metadata only: what the run is pinned to, each identifier copyable. */
export function RunDetails({ run }: { run: RunView }) {
  const t = (s?: string) => (s ? new Date(s).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—");
  return (
    <div className="card">
      <h2>Details</h2>
      <dl className="kv">
        <dt>Repository</dt><dd><a href={`https://github.com/${run.issue.repo}`}>{run.issue.repo}</a></dd>
        <dt>Issue</dt><dd><a href={run.issue.html_url}>#{run.issue.number}</a></dd>
        <dt><span data-tip="The exact commit PatchPilot cloned and tested. The pull request is based on it." tabIndex={0}>Base commit</span></dt>
        <dd><code title={run.base_sha}>{run.base_sha?.slice(0, 10) || "—"}</code>{run.base_sha && <CopyButton text={run.base_sha} label="Commit" />}</dd>
        <dt><span data-tip="Goes up by one each time you ask for a revision. Approval is tied to one revision." tabIndex={0}>Revision</span></dt><dd><span>{run.revision ?? 0}</span></dd>
        <dt>Started</dt><dd><span>{t(run.created_at)}</span></dd>
        <dt>Updated</dt><dd><span>{t(run.updated_at)}</span></dd>
        <dt>Run</dt><dd><code title={run.run_id}>{run.run_id.slice(0, 8)}</code><CopyButton text={run.run_id} label="Run id" /></dd>
      </dl>
    </div>
  );
}
