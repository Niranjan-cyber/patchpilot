import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "./api";
import type { IssueCheck as Check, RunView } from "./contracts";
import { AssessmentCard, Loading, Status, StatusIcon } from "./components";

// #70 item 7: one row per dimension; they explain the decision above, there is no overall score
type Dim = { dimension: string; outcome: "ok" | "concern" | "blocker" | "unknown"; explanation: string;
  evidence: { source: string; text: string; url?: string }[]; missing: string[] };
const DIM: Record<string, string> = {
  problem_clarity: "Is it a bug?", expected_behavior: "Expected behaviour", reproducibility: "Can it be reproduced?",
  technical_scope: "How big is the change?", repo_compatibility: "Can PatchPilot set up the project?", testability: "Can a fix be tested?",
  maintainer_intent: "Do the maintainers want a fix?", existing_work: "Is someone already on it?", system_support: "Is it within what PatchPilot handles?",
};
// amber for "check this", never green for unknown (DESIGN.md)
const OUTCOME = { ok: ["passed", "Looks fine"], concern: ["inconclusive", "Check this"], blocker: ["failed", "Stops a fix"],
  unknown: ["not_run", "Unknown"] } as const;
const SOURCE: Record<string, string> = { reporter: "Reporter", maintainer: "Maintainer", contributor: "Another commenter",
  repository: "Repository", patchpilot: "PatchPilot (may be wrong)" };

function Suitability({ dims }: { dims?: Dim[] | null }) {
  if (!dims?.length) return null;
  return (
    <details className="card suitability">
      <summary>How we judged it, one question at a time</summary>
      <p className="hint">Each line says whose words or which check it comes from. A maintainer decision is only ever a maintainer's own words.</p>
      <ul>
        {dims.map((d) => {
          const [cls, word] = OUTCOME[d.outcome];
          return (
            <li key={d.dimension}>
              <span className={`status status-${cls}`}><StatusIcon s={cls} size={12} />{word}</span> <strong>{DIM[d.dimension] ?? d.dimension}</strong>
              <p>{d.explanation}</p>
              {(d.evidence.length > 0 || d.missing.length > 0) && (
                <ul className="hint">
                  {d.evidence.map((e, i) => <li key={i}>{SOURCE[e.source] ?? e.source}: {e.url ? <a href={e.url}>{e.text}</a> : e.text}</li>)}
                  {d.missing.map((m, i) => <li key={`m${i}`}>Missing: {m}</li>)}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

const CHECKS: Record<string, string> = {
  open: "The issue is open", public: "The repository is public", python: "It's a Python project",
  tests_found: "The project has tests", unassigned: "Nobody is assigned to it or has said they're fixing it", no_linked_pr: "No open pull request already fixes it",
};
const WARN: Record<string, string> = {
  closed: "This issue is closed. Someone may have already fixed it or decided not to.",
  assigned: "Someone is assigned to this issue, or said in a comment that they're fixing it or sending a pull request. Ask on the issue before starting.",
  linked_pr: "An open pull request already mentions this issue. Check it before starting.",
  already_fixed: "A merged pull request already references this issue. It may be fixed and just not closed yet. Check before starting.",
  prs_collaborators_only: "This repository only accepts pull requests from its own collaborators, so you can't open one here. You can still ask on the issue or share the fix.",
  lookup_failed: "Some checks couldn't be completed. Results marked Inconclusive are unknown, not passed.",
  needs_info: "The issue is missing details a test needs (see above). PatchPilot may not be able to reproduce it.",
  unclear_type: "We couldn't tell whether this is a bug. Fixes are only attempted for bugs and regressions.",
  base_unknown: "We couldn't read the repository's latest commit, so we don't know exactly which code a run would use.",
  other_os: "This seems to happen only on Windows or macOS. Our sandbox runs Linux, so we may not be able to reproduce it.",
};

export default function IssueCheck() {
  const [params] = useSearchParams();
  const url = params.get("url") ?? "";
  const nav = useNavigate();
  const [chk, setChk] = useState<Check | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [starting, setStarting] = useState<string | null>(null);

  const load = () => {
    setChk(null); setErr(null);
    api<Check>("/api/issues/check", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ url }) })
      .then(setChk).catch(setErr);
  };
  useEffect(load, [url]);

  // assessmentOnly: "Save the assessment report" tells the server never to queue a job, even if a re-check now says READY
  const start = async (assessmentOnly = false) => {
    setStarting(assessmentOnly ? "Saving…" : "Starting…");
    try {
      const run = await api<RunView>("/api/runs", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ issue_url: url, continue_despite: accepted ? chk?.warnings ?? [] : [], assessment_only: assessmentOnly }),
      });
      nav(`/runs/${run.run_id}`);
    } catch (e) { setStarting(null); setErr(e as ApiError); }
  };

  if (err && !chk) return (
    <section className="panel failed">
      <h1>{err.code === "GITHUB_UNAVAILABLE" ? "GitHub didn't answer" : "We can't check that link"}</h1>
      <p>{err.message}</p>
      <div className="row">{err.code === "GITHUB_UNAVAILABLE" && <button onClick={load}>Try again</button>}<Link to="/" className="button secondary">Paste a different link</Link></div>
    </section>
  );
  if (!chk) return <Loading label="Reading the issue and checking the repository…" />;

  const i = chk.issue;
  const a = chk.assessment;
  // UNSUPPORTED / ASSESSMENT_ONLY: nothing runs; "Save the assessment" creates a finished report run (contracts v0.4)
  const assessOnly = !!a && (a.handling_decision === "UNSUPPORTED" || a.handling_decision === "ASSESSMENT_ONLY");
  const blocked = !!chk.unsupported && !a;
  const warned = (chk.warnings ?? []).length > 0;
  return (
    <section className="check">
      <p className="issue-ref"><a href={i.html_url}>{i.repo} #{i.number}</a>{chk.language ? `, ${chk.language}` : ""}</p>
      <h1>{i.title}</h1>
      {(i.expected || i.actual) ? (
        <dl className="ea">
          {i.expected && <><dt>Expected</dt><dd>{i.expected}</dd></>}
          {i.actual && <><dt>What happens instead</dt><dd>{i.actual}</dd></>}
        </dl>
      ) : <p className="hint">The issue doesn't spell out expected and actual behaviour; PatchPilot will work from the description.</p>}

      <div className="card">
        <h2>Is this a good issue to work on?</h2>
        <ul className="checks">
          {Object.entries(CHECKS).map(([k, label]) => (
            <li key={k}><Status s={(i.checks ?? {})[k] as never} /> <span>{label}</span></li>
          ))}
        </ul>
        {chk.base_sha && <p className="hint">We'll work on commit <code>{chk.base_sha.slice(0, 7)}</code> of {chk.default_branch}.</p>}
      </div>

      <AssessmentCard a={a} />
      <Suitability dims={chk.suitability as Dim[] | null | undefined} />

      {chk.policy?.ai_policy === "forbidden" && (
        <p className="notice warn">This repository's contribution rules don't accept AI-assisted pull requests. You can still run PatchPilot and keep the report, but publishing will be turned off. (Our reading of {chk.policy.source_evidence_ids?.join(", ")}.)</p>
      )}
      {blocked && (
        <div className="notice warn">
          <p>{chk.unsupported === "not_python" ? "PatchPilot can only run Python projects today." : "We couldn't find any tests in this repository, so we can't verify a fix."}</p>
          <Link to="/">Try another issue</Link>
        </div>
      )}
      {!blocked && !assessOnly && warned && (
        <div className="notice warn">
          <ul>{chk.warnings!.map((w) => <li key={w}>{WARN[w] ?? w}</li>)}</ul>
          <label className="accept"><input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} /> I understand, start anyway</label>
        </div>
      )}
      {assessOnly && (
        <div className="row">
          <button onClick={() => start(true)} disabled={!!starting}>{starting ?? "Save the assessment report"}</button>
          <Link to="/" className="button secondary">Find another issue</Link>
        </div>
      )}
      {!blocked && !assessOnly && (
        <div className="row">
          <button onClick={() => start()} disabled={!!starting || (warned && !accepted)}>{starting ?? "Start run"}</button>
          <Link to="/" className="button secondary">Find another issue</Link>
        </div>
      )}
      {err && <p className="notice warn">{err.message}</p>}
      <p className="hint">A run usually takes 4–15 minutes. Nothing is published unless you approve it at the end.</p>
    </section>
  );
}
