import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, SHOWCASE, useRun } from "./api";
import { AssessmentCard, Icon, LiveStatus, Loading, Mark, ProofPanel, RunDetails, SampleBadge, Stepper, VerdictNote } from "./components";
import IssueCheck from "./IssueCheck";
import Review from "./Review";
import { Connect, PrOpened } from "./Publish";
import MyRuns, { RunList, useMyRuns } from "./MyRuns";
import Eval from "./Eval";
import { AttemptHistory, DiagnosisCard } from "./Diagnosis";
import AskPanel from "./Ask";
import { GuidedPauseNotice, PauseToggles } from "./Pauses";
import ExtraChecks from "./ExtraChecks";
import { RunHeader } from "./RunNav";
import Explore from "./Explore";

const NAV = [
  { to: "/", label: "New run", icon: "plus", end: true },
  { to: "/my-runs", label: "My runs", icon: "list" },
  { to: "/explore", label: "Explore a repo", icon: "search" },
  { to: "/eval", label: "Accuracy", icon: "gauge" },
] as const;

function Shell({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<{ signed_in: boolean; login: string | null } | null>(null);
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => { api<{ signed_in: boolean; login: string | null }>("/api/me").then(setMe).catch(() => setMe(null)); }, []);
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {   // Escape closes the phone menu
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  return (
    <div className={`app${open ? " nav-open" : ""}`}>
      <div className="mobile-bar">
        <Link to="/" className="brand"><Mark size={20} />PatchPilot</Link>
        <button className="secondary" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(!open)}>
          <Icon name={open ? "x" : "menu"} />{open ? "Close" : "Menu"}
        </button>
      </div>
      <nav className="sidebar" id="sidebar" aria-label="Main">
        <Link to="/" className="brand"><Mark />PatchPilot</Link>
        <ul className="navlist">
          {NAV.map((n) => <li key={n.to}><NavLink to={n.to} end={"end" in n}><Icon name={n.icon} />{n.label}</NavLink></li>)}
        </ul>
        <div className="side-foot">
          {me?.signed_in ? (
            <div className="account"><span className="avatar" aria-hidden>{(me.login ?? "?")[0].toUpperCase()}</span>Signed in as {me.login}</div>
          ) : (
            <ul className="navlist"><li><NavLink to="/connect"><Icon name="github" />Sign in with GitHub</NavLink></li></ul>
          )}
          <p className="host-note">{SHOWCASE ? "Showcase: recorded runs, read-only." : "Runs on a demo machine and may stop if it goes offline."}</p>
        </div>
      </nav>
      <div className="sheet"><main>{children}</main></div>
    </div>
  );
}

// A real, planted bug in the team's demo repo: one click shows the whole flow on an issue PatchPilot is known to fix.
const TRY = "https://github.com/Niranjan-cyber/tinycalc/issues/1";
const HOW = [
  ["search", "Check the issue", "Is it a clear bug, in a Python project with tests, that nobody is already fixing?"],
  ["x", "Reproduce it", "A new test must fail twice on the original code, in a sandbox with no network."],
  ["check", "Fix and prove it", "The same test must pass twice after the fix, and existing tests must still pass, in a fresh sandbox."],
  ["file", "You review and decide", "Read the exact change. Nothing reaches GitHub until you approve it."],
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
        <h1>New run</h1>
        <p className="lede">Paste a GitHub issue. PatchPilot reproduces the bug, tests a fix, and shows you the proof before anything is published.</p>
        <form onSubmit={(e) => { e.preventDefault(); check(url); }} className="paste">
          <label htmlFor="issue">GitHub issue link</label>
          <div className="paste-row">
            <input id="issue" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repo/issues/123" required aria-describedby="issue-hint" />
            <button type="submit">Check issue</button>
          </div>
          <p className="hint" id="issue-hint">Public Python projects with pytest tests. Other projects get an assessment, not a fix.</p>
          <p className="try">No issue in mind? <button type="button" className="linkbtn" onClick={() => check(TRY)}>Try tinycalc #1</button>: divide(x, 0) returns 0 instead of raising.</p>
        </form>
      </div>
      <div className="start-grid">
        <section aria-labelledby="recent">
          <div className="section-head"><h2 id="recent">Your recent runs</h2>{!!mine.items?.length && <Link to="/my-runs">View all</Link>}</div>
          {mine.items?.length ? <RunList items={mine.items.slice(0, 5)} />
            : <p className="verdict-note">No runs yet in this browser. Runs you start appear here, and they keep going if you close the page.</p>}
        </section>
        <section aria-labelledby="how">
          <h2 id="how">What a run does</h2>
          <ol className="how">
            {HOW.map(([, t, d]) => <li key={t}><strong>{t}</strong><span>{d}</span></li>)}
          </ol>
        </section>
      </div>
      {fixtures.length > 0 && (
        <section className="samples" aria-labelledby="samples">
          <h2 id="samples" className="with-badge">Sample runs <SampleBadge /></h2>
          <p className="hint">Recorded examples of every way a run can end, including the ones that don't produce a fix.</p>
          <ul className="sample-grid">{fixtures.map((f) => <li key={f}><Link to={`/runs/${f}`}>{f[0].toUpperCase() + f.slice(1).replaceAll("_", " ")}</Link></li>)}</ul>
        </section>
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
  const assessed = run.outcome === "ASSESSMENT_ONLY";   // nothing ran: the assessment is the whole report
  return (
    <section className="run-page">
      <RunHeader run={run} id={id} />
      <div className="run-grid">
        <div className="run-main">
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
          <section className="chapter verdict" aria-labelledby="proof-h">
            <div className="section-head"><h2 id="proof-h">{done ? "Proof" : "Progress"}</h2></div>
            {done ? <div className="stack"><ProofPanel run={run} /><VerdictNote run={run} /></div> : <LiveStatus run={run} />}
          </section>
          {assessed && <AssessmentCard a={run.assessment} />}
          {!assessed && (
            <section aria-labelledby="steps-h">
              <div className="section-head"><h2 id="steps-h">Steps</h2><span className="hint">Each status is recorded by code, not by the AI</span></div>
              <Stepper run={run} />
            </section>
          )}
          {done && <ExtraChecks run={run} />}
        </div>
        <aside className="side" aria-label="About this run">
          <DiagnosisCard run={run} />
          <RunDetails run={run} />
          <AttemptHistory events={events} />
          <AskPanel run={run} />
          <PauseToggles run={run} />
          {done && <a className="button secondary" href={`/api/runs/${id}/report.md`}><Icon name="file" />Download report</a>}
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
