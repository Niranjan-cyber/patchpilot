import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "./api";
import type { IssueCheck as Check, RunView } from "./contracts";
import { Loading, Status } from "./components";

const CHECKS: Record<string, string> = {
  open: "The issue is open", public: "The repository is public", python: "It's a Python project",
  tests_found: "The project has tests", unassigned: "Nobody is assigned to it", no_linked_pr: "No open pull request already fixes it",
};
const WARN: Record<string, string> = {
  closed: "This issue is closed. Someone may have already fixed it or decided not to.",
  assigned: "Someone is assigned to this issue and may already be working on it.",
  linked_pr: "An open pull request already mentions this issue. Check it before starting.",
  lookup_failed: "Some checks couldn't be completed. Results marked Inconclusive are unknown, not passed.",
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

  const start = async () => {
    setStarting("Starting…");
    try {
      const run = await api<RunView>("/api/runs", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ issue_url: url, continue_despite: accepted ? chk?.warnings ?? [] : [] }),
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
  const blocked = !!chk.unsupported;
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

      {chk.policy?.ai_policy === "forbidden" && (
        <p className="notice warn">This repository's contribution rules don't accept AI-assisted pull requests. You can still run PatchPilot and keep the report, but publishing will be turned off. (Our reading of {chk.policy.source_evidence_ids?.join(", ")}.)</p>
      )}
      {blocked && (
        <div className="notice warn">
          <p>{chk.unsupported === "not_python" ? "PatchPilot can only run Python projects today." : "We couldn't find any tests in this repository, so we can't verify a fix."}</p>
          <Link to="/">Try another issue</Link>
        </div>
      )}
      {!blocked && warned && (
        <div className="notice warn">
          <ul>{chk.warnings!.map((w) => <li key={w}>{WARN[w] ?? w}</li>)}</ul>
          <label className="accept"><input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} /> I understand, start anyway</label>
        </div>
      )}
      {!blocked && (
        <div className="row">
          <button onClick={start} disabled={!!starting || (warned && !accepted)}>{starting ?? "Start run"}</button>
          <Link to="/" className="button secondary">Find another issue</Link>
        </div>
      )}
      {err && <p className="notice warn">{err.message}</p>}
      <p className="hint">A run usually takes 4–15 minutes. Nothing is published unless you approve it at the end.</p>
    </section>
  );
}
