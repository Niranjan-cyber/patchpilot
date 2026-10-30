import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, SHOWCASE, useRun } from "./api";
import { LiveStatus, Loading, ProofPanel, ReadinessBadge, SampleBadge, Stepper, VerdictNote } from "./components";
import IssueCheck from "./IssueCheck";
import Review from "./Review";
import { Connect, PrOpened } from "./Publish";
import MyRuns, { RunList, useMyRuns } from "./MyRuns";
import Eval from "./Eval";
import { AttemptHistory, DiagnosisCard } from "./Diagnosis";
import AskPanel from "./Ask";
import { GuidedPauseNotice, PauseToggles } from "./Pauses";
import ExtraChecks from "./ExtraChecks";
import Explore from "./Explore";

function Shell({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<{ signed_in: boolean; login: string | null } | null>(null);
  useEffect(() => { api<{ signed_in: boolean; login: string | null }>("/api/me").then(setMe).catch(() => setMe(null)); }, []);
  return (
    <>
      <div className="demo-banner">{SHOWCASE ? "Showcase: real recorded runs, read-only. New runs need the live app on our demo machine." : "Running on a demo machine. Runs may stop if it goes offline."}</div>
      <header className="top">
        <Link to="/" className="brand">PatchPilot</Link>
        <nav>
          <NavLink to="/">New run</NavLink>
          <NavLink to="/explore">Explore a repo</NavLink>
          <NavLink to="/my-runs">My runs</NavLink>
          <NavLink to="/eval">Accuracy</NavLink>
          {me?.signed_in ? <span className="hint">Signed in as {me.login}</span> : <NavLink to="/connect">Sign in with GitHub</NavLink>}
        </nav>
      </header>
      <main>{children}</main>
    </>
  );
}

// A real, planted bug in the team's demo repo: one click shows the whole flow on an issue PatchPilot is known to fix.
const TRY = "https://github.com/Niranjan-cyber/tinycalc/issues/1";
const HOW = [
  ["Paste an issue", "Any public GitHub issue on a Python project with tests."],
  ["Watch the proof", "We reproduce the bug in a locked-down sandbox, fix it, and run the same test before and after."],
  ["Approve a draft pull request", "You read the exact change. Nothing is published until you say so."],
] as const;

function Start() {
  const [url, setUrl] = useState("");
  const [fixtures, setFixtures] = useState<string[]>([]);
  const nav = useNavigate();
  const mine = useMyRuns();
  useEffect(() => { api<string[]>("/api/fixtures").then(setFixtures).catch(() => setFixtures([])); }, []);
  const check = (u: string) => nav(`/check?url=${encodeURIComponent(u)}`);
  return (
    <section className="start">
      <div className="hero">
        <h1>Turn a GitHub issue into a tested fix.</h1>
        <p className="lede">We reproduce the bug in a sandbox, test a fix, and show you the proof. You decide whether to open a pull request.</p>
        <form onSubmit={(e) => { e.preventDefault(); check(url); }} className="paste">
          <label htmlFor="issue">GitHub issue link</label>
          <div className="paste-row">
            <input id="issue" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repo/issues/123" required />
            <button type="submit">Check issue</button>
          </div>
          <p className="hint">Works today on public Python projects with tests. Other projects get a report, not a fix.</p>
          <p className="try">New here? <button type="button" className="linkbtn" onClick={() => check(TRY)}>Try it on a real bug</button>
            <span className="hint"> tinycalc #1: divide(x, 0) returns 0 instead of raising</span></p>
        </form>
        <ol className="how" aria-label="How a run works">
          {HOW.map(([t, d]) => <li key={t}><strong>{t}</strong><span>{d}</span></li>)}
        </ol>
      </div>
      <section className="preview" aria-label="What a finished run shows you">
        <div>
          <h2>Every fix comes with proof</h2>
          <p className="hint">The same new test, run twice on the original code and twice on the fix, each time in a fresh sandbox. From a real run on tinycalc #1.</p>
        </div>
        <div className="mini-proof" aria-hidden>
          <span className="run run-failed">Run 1: Failed</span><span className="run run-failed">Run 2: Failed</span>
          <span className="mini-arrow">➜</span>
          <span className="run run-passed">Run 1: Passed</span><span className="run run-passed">Run 2: Passed</span>
        </div>
      </section>
      {!!mine.items?.length && (
        <div className="samples"><h2>Your recent runs</h2><RunList items={mine.items.slice(0, 5)} /></div>
      )}
      {fixtures.length > 0 && (
        <div className="samples">
          <h2>Sample runs <SampleBadge /></h2>
          <p className="hint">Recorded examples of every way a run can end, including the ones that don't produce a fix.</p>
          <ul className="sample-grid">{fixtures.map((f) => <li key={f}><Link to={`/runs/${f}`}>{f[0].toUpperCase() + f.slice(1).replaceAll("_", " ")}</Link></li>)}</ul>
        </div>
      )}
    </section>
  );
}

function Run() {
  const { id = "" } = useParams();
  const { run, events, error } = useRun(id);
  if (error) return <section className="panel failed"><h1>Couldn't load this run</h1><p>{error.message}</p><Link className="button" to="/">Start a new run</Link></section>;
  if (!run) return <Loading label="Loading the run…" />;
  const done = !!run.outcome;
  const real = /^[0-9a-f-]{36}$/.test(id);
  const next = run.status === "awaiting_approval" || !!run.pr;
  return (
    <section className="run-page">
      <div className="chapter verdict">
        <div className="run-head">
          <div>
            <p className="issue-ref"><a href={run.issue.html_url}>{run.issue.repo} #{run.issue.number}</a> {!real && <SampleBadge />}</p>
            <h1>{run.issue.title}</h1>
          </div>
          <ReadinessBadge run={run} />
        </div>
        {done ? <><ProofPanel run={run} /><VerdictNote run={run} /></> : <LiveStatus run={run} />}
      </div>
      <GuidedPauseNotice run={run} />
      {run.status === "paused" && run.pause?.reason !== "guided_pause" && (
        <p className="notice warn">
          {run.pause?.resume_at ? `Paused: free AI capacity resumes around ${new Date(run.pause.resume_at).toLocaleTimeString()}.`
            : "Paused until free AI capacity is available. We'll stop and keep your report if that takes over 2 hours."}
        </p>
      )}
      {run.supplyguard?.status === "inconclusive" && (
        <p className="notice warn">We couldn't fully check this project's dependencies, so publishing is turned off.</p>
      )}
      {done && <ExtraChecks run={run} />}
      <div className="run-grid">
        <Stepper run={run} />
        <aside className="side">
          {next && (
            <div className="card next-card">
              <h2>Your next step</h2>
              {run.status === "awaiting_approval" && !run.approval && <p>Read the exact change and decide. Nothing is published until you approve.</p>}
              {run.status === "awaiting_approval" && <Link className="button" to={`/runs/${id}/review`}>Review and approve</Link>}
              {run.status === "awaiting_approval" && run.approval && <Link className="button" to={`/connect?run=${id}`}>Publish draft pull request</Link>}
              {run.pr && <Link className="button" to={`/runs/${id}/pr`}>See the pull request</Link>}
            </div>
          )}
          <DiagnosisCard run={run} />
          <AttemptHistory events={events} />
          <AskPanel run={run} />
          <PauseToggles run={run} />
          {done && <a className="button secondary" href={`/api/runs/${id}/report.md`}>Download report</a>}
          {!done && <p className="hint">Runs usually take 4–15 minutes. You can leave this page; the run keeps going.</p>}
          {!done && real && (
            <button className="danger-btn" onClick={() => api(`/api/runs/${id}/stop`, { method: "POST" }).catch(() => null)}>
              Stop run and keep the report so far
            </button>
          )}
          {run.details_expired_at && <p className="notice">This run's details have expired. The outcome and pull request link are kept.</p>}
        </aside>
      </div>
    </section>
  );
}

const Stub = ({ title, children }: { title: string; children?: React.ReactNode }) => (
  <section className="panel empty"><h1>{title}</h1>{children}</section>
);

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Start />} />
        <Route path="/check" element={<IssueCheck />} />
        <Route path="/runs/:id" element={<Run />} />
        <Route path="/runs/:id/review" element={<Review />} />
        <Route path="/connect" element={<Connect />} />
        <Route path="/runs/:id/pr" element={<PrOpened />} />
        <Route path="/my-runs" element={<MyRuns />} />
        <Route path="/eval" element={<Eval />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="*" element={<Stub title="Page not found"><p>This link doesn't match any page. Runs open from My runs, or start a new one.</p>
          <div className="row"><Link className="button" to="/">Start a new run</Link><Link className="button secondary" to="/my-runs">My runs</Link></div></Stub>} />
      </Routes>
    </Shell>
  );
}
