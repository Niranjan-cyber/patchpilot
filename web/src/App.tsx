import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, SHOWCASE, useRun } from "./api";
import { AssessmentCard, Icon, LiveStatus, Loading, Mark, ProofPanel, SampleBadge, VerdictNote } from "./components";
import IssueCheck from "./IssueCheck";
import Review from "./Review";
import { Connect, PrOpened } from "./Publish";
import MyRuns, { useMyRuns } from "./MyRuns";
import Eval from "./Eval";
import { AttemptHistory, DiagnosisCard } from "./Diagnosis";
import AskPanel from "./Ask";
import { GuidedPauseNotice, PauseToggles } from "./Pauses";
import ExtraChecks from "./ExtraChecks";
import Explore from "./Explore";
import { RunHeader } from "./RunNav";
import { ActivityButton, Findings, RunDetails, StageNavigator } from "./Workspace";
import { Modal, ToastProvider, useIndicator } from "./ui";

const NAV = [
  { to: "/", label: "Overview", icon: "gauge", end: true },
  { to: "/my-runs", label: "My runs", icon: "list" },
  { to: "/explore", label: "Explore a repo", icon: "search" },
  { to: "/eval", label: "Accuracy", icon: "shield" },
] as const;

function Shell({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<{ signed_in: boolean; login: string | null } | null>(null);
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const mine = useMyRuns();
  const waiting = mine.items?.filter((i) => i.status === "awaiting_approval").length ?? 0;   // a count only on a queue that needs you
  const { box, style } = useIndicator<HTMLUListElement>("a.active", [loc.pathname], "y");
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
        <ul className="navlist" ref={box}>
          <span className="nav-pill" style={style} aria-hidden />
          {NAV.map((n) => (
            <li key={n.to}><NavLink to={n.to} end={"end" in n}><Icon name={n.icon} />{n.label}
              {n.to === "/my-runs" && waiting > 0 && <span className="count" aria-label={`${waiting} waiting for your approval`}>{waiting}</span>}</NavLink></li>
          ))}
        </ul>
        <div className="side-foot">
          {me?.signed_in ? (
            <div className="account"><span className="avatar" aria-hidden>{(me.login ?? "?")[0].toUpperCase()}</span>{me.login}</div>
          ) : (
            <ul className="navlist"><li><NavLink to="/connect"><Icon name="github" />Sign in with GitHub</NavLink></li></ul>
          )}
          <p className="host-note">{SHOWCASE ? "Showcase: recorded runs, read-only." : "Live on a demo machine. Runs stop if it goes offline."}</p>
        </div>
      </nav>
      <div className="sheet"><main key={loc.pathname}>{children}</main></div>
    </div>
  );
}

// A real, planted bug in the team's demo repo: one click shows the whole flow on an issue PatchPilot is known to fix.
const TRY = "https://github.com/Niranjan-cyber/tinycalc/issues/1";
const FLOW = [["search", "Check the issue"], ["x", "Reproduce, fails twice"], ["check", "Fix, passes twice"], ["eye", "Independent review"], ["github", "You approve a draft PR"]] as const;
const ISSUE_RE = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/issues\/\d+\/?$/;
/** Accepts a full issue URL or owner/repo#123. */
const normalise = (s: string) => {
  const t = s.trim(); const m = /^([\w.-]+)\/([\w.-]+)#(\d+)$/.exec(t);
  return m ? `https://github.com/${m[1]}/${m[2]}/issues/${m[3]}` : t;
};

function Overview() {
  const [url, setUrl] = useState("");
  const [touched, setTouched] = useState(false);
  const [fixtures, setFixtures] = useState<string[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const nav = useNavigate();
  const mine = useMyRuns();
  useEffect(() => { api<string[]>("/api/fixtures").then(setFixtures).catch(() => setFixtures([])); }, []);
  useEffect(() => {   // "/" jumps to the issue field, like most developer tools
    const k = (e: KeyboardEvent) => { if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") { e.preventDefault(); input.current?.focus(); } };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  const target = normalise(url);
  const bad = touched && url.trim() !== "" && !ISSUE_RE.test(target);
  const check = (u: string) => nav(`/check?url=${encodeURIComponent(u)}`);
  const items = mine.items ?? [];
  const attention = items.filter((i) => i.status === "awaiting_approval");
  const active = items.filter((i) => !i.outcome && i.status !== "awaiting_approval");
  const done = items.filter((i) => !!i.outcome && i.status !== "awaiting_approval").slice(0, 5);
  const card = (i: (typeof items)[number], cls = "") => (
    <Link key={i.run_id} to={`/runs/${i.run_id}`} className={`card interactive runcard ${cls}`}>
      <strong>{i.title}</strong>
      <span className="meta">{i.repo}#{i.number} · {new Date(i.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</span>
      <span className={`pill pill-${i.status}`}>{i.status === "awaiting_approval" ? "Needs your approval" : i.readiness ?? (i.status === "queued" ? "Waiting to start" : i.status === "paused" ? "Paused" : "Running")}</span>
    </Link>
  );
  return (
    <section className="start">
      <div className="launch">
        <h1>Turn an issue into a verified fix</h1>
        <p className="lede">PatchPilot reproduces the bug in a sandbox, tests a fix against the same failing test, and shows you the evidence. Nothing reaches GitHub until you approve it.</p>
        <form noValidate onSubmit={(e) => { e.preventDefault(); setTouched(true); if (ISSUE_RE.test(target)) check(target); }} className="paste">
          <label htmlFor="issue">GitHub issue link</label>
          <div className="paste-row">
            <input id="issue" ref={input} value={url} onChange={(e) => setUrl(e.target.value)} onBlur={() => setTouched(true)} placeholder="https://github.com/owner/repo/issues/123"
              aria-invalid={bad} aria-describedby="issue-hint" autoComplete="off" spellCheck={false} />
            <button type="submit"><Icon name="arrow" />Check issue</button>
          </div>
          {bad ? <p className="field-error" id="issue-hint" role="alert">That isn't a GitHub issue link. It should look like github.com/owner/repo/issues/123.</p>
            : <p className="hint" id="issue-hint" style={{ marginTop: 8 }}>A link or owner/repo#123. Public Python projects with pytest tests; others get an assessment, not a fix. Press <kbd>/</kbd> to jump here.</p>}
          <p className="try">No issue in mind? <button type="button" className="linkbtn" onClick={() => check(TRY)}>Try tinycalc #1</button>: divide(x, 0) returns 0 instead of raising.</p>
        </form>
        <ol className="flow" aria-label="What a run does">{FLOW.map(([i, t]) => <li key={t}><Icon name={i} size={14} />{t}</li>)}</ol>
      </div>

      <div className="dash">
        <div>
          {mine.items === null ? <div className="lane"><span className="hint">Loading your runs…</span></div> : (
            <>
              <div className="lane">
                <div className="section-head"><h2>Needs your attention</h2><span className="hint">{attention.length}</span></div>
                {attention.length ? attention.map((i) => card(i, "attention")) : <p className="lane-empty">Nothing is waiting for you. Runs that need your approval appear here.</p>}
              </div>
              <div className="lane">
                <div className="section-head"><h2>In progress</h2><span className="hint">{active.length}</span></div>
                {active.length ? active.map((i) => card(i)) : <p className="lane-empty">No runs are working right now.</p>}
              </div>
              <div className="lane">
                <div className="section-head"><h2>Recently finished</h2>{items.length > 0 && <Link to="/my-runs">View all</Link>}</div>
                {done.length ? done.map((i) => card(i)) : <p className="lane-empty">Finished runs land here with their verdict and report.</p>}
              </div>
            </>
          )}
        </div>
        <aside className="card">
          <h2>What PatchPilot checks</h2>
          <ol className="how">
            <li><strong>Is it worth fixing?</strong><span>A clear bug in a Python project with tests, that nobody has claimed and no open PR already fixes.</span></li>
            <li><strong>Can it be proven?</strong><span>A new test must fail twice on the original code, in a sandbox with no network.</span></li>
            <li><strong>Does the fix hold?</strong><span>The same test passes twice in a fresh sandbox, and every test that passed before still passes.</span></li>
            <li><strong>Would a maintainer accept it?</strong><span>An independent reviewer reads the diff, and you approve the exact change before anything is published.</span></li>
          </ol>
        </aside>
      </div>

      {fixtures.length > 0 && (
        <section className="samples" aria-labelledby="samples">
          <h2 id="samples" className="with-badge">Sample runs <SampleBadge /></h2>
          <p className="hint">Recorded examples of every way a run can end, including the ones that don't produce a fix.</p>
          <ul className="sample-grid">{fixtures.map((f) => <li key={f}><Link to={`/runs/${f}`}>{f[0].toUpperCase() + f.slice(1).replaceAll("_", " ")}<Icon name="chev" size={14} /></Link></li>)}</ul>
        </section>
      )}
    </section>
  );
}

function Run() {
  const { id = "" } = useParams();
  const { run, events, error } = useRun(id);
  const [confirmStop, setConfirmStop] = useState(false);
  if (error) return <section className="panel failed"><h1>Couldn't load this run</h1><p>{error.message}</p><Link className="button" to="/">Back to overview</Link></section>;
  if (!run) return <Loading label="Loading the run…" />;
  const done = !!run.outcome;
  const real = /^[0-9a-f-]{36}$/.test(id);
  const assessed = run.outcome === "ASSESSMENT_ONLY";   // nothing ran: the assessment is the whole report
  const next = run.pr ? { to: `/runs/${id}/pr`, t: "Pull request opened", d: "See the draft pull request and what happens next.", b: "See the pull request" }
    : run.status === "awaiting_approval" && run.approval ? { to: `/connect?run=${id}`, t: "Approved, ready to publish", d: "Connect GitHub to open a draft pull request with exactly this change.", b: "Publish draft pull request" }
    : run.status === "awaiting_approval" ? { to: `/runs/${id}/review`, t: "Your decision", d: "Read the exact change and decide. Nothing is published until you approve.", b: "Review and approve" } : null;
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
            <div className="section-head"><h2 id="proof-h"><Icon name="flask" />{done ? "Proof" : "Progress"}</h2>
              {done && run.repro?.runs_on_base?.length ? <span className="hint">Same test, before and after, each run in its own sandbox</span> : null}</div>
            {done ? <div className="stack"><ProofPanel run={run} /><VerdictNote run={run} /></div> : <LiveStatus run={run} />}
          </section>
          {assessed && <AssessmentCard a={run.assessment} />}
          {!assessed && (
            <section aria-labelledby="steps-h">
              <div className="section-head"><h2 id="steps-h"><Icon name="terminal" />Stages</h2><ActivityButton events={events} /></div>
              <StageNavigator run={run} />
            </section>
          )}
          {!assessed && (done || run.review) && <Findings run={run} />}
          {done && <ExtraChecks run={run} />}
        </div>
        <aside className="side" aria-label="About this run">
          {next && (
            <div className="card next-card">
              <h2>{next.t}</h2>
              <p>{next.d}</p>
              <Link className="button" to={next.to}>{next.b}<Icon name="arrow" /></Link>
            </div>
          )}
          <DiagnosisCard run={run} />
          <RunDetails run={run} />
          <AttemptHistory events={events} />
          <AskPanel run={run} />
          <PauseToggles run={run} />
          {done && <a className="button secondary" href={`/api/runs/${id}/report.md`}><Icon name="file" />Download report</a>}
          {!done && <p className="hint">Runs usually take 4–15 minutes. You can leave this page; the run keeps going.</p>}
          {!done && real && <button className="danger-btn" onClick={() => setConfirmStop(true)}><Icon name="stop" />Stop run</button>}
          {run.details_expired_at && <p className="notice">This run's details have expired. The outcome and pull request link are kept.</p>}
        </aside>
      </div>
      <Modal open={confirmStop} onClose={() => setConfirmStop(false)} title="Stop this run?"
        actions={<>
          <button className="secondary" onClick={() => setConfirmStop(false)}>Keep running</button>
          <button className="danger-solid" onClick={() => { setConfirmStop(false); api(`/api/runs/${id}/stop`, { method: "POST" }).catch(() => null); }}>Stop run</button>
        </>}>
        <p>The run ends where it is and keeps its report so far. A stopped run can never be published; you'd start a new run to try again.</p>
      </Modal>
    </section>
  );
}

const Stub = ({ title, children }: { title: string; children?: React.ReactNode }) => (
  <section className="panel empty"><h1>{title}</h1>{children}</section>
);

export default function App() {
  return (
    <ToastProvider>
      <Shell>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/check" element={<IssueCheck />} />
          <Route path="/runs/:id" element={<Run />} />
          <Route path="/runs/:id/review" element={<Review />} />
          <Route path="/connect" element={<Connect />} />
          <Route path="/runs/:id/pr" element={<PrOpened />} />
          <Route path="/my-runs" element={<MyRuns />} />
          <Route path="/eval" element={<Eval />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="*" element={<Stub title="Page not found"><p>This link doesn't match any page. Runs open from My runs, or start a new one.</p>
            <div className="row"><Link className="button" to="/">Back to overview</Link><Link className="button secondary" to="/my-runs">My runs</Link></div></Stub>} />
        </Routes>
      </Shell>
    </ToastProvider>
  );
}
