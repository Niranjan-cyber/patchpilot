import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion, MotionConfig } from "motion/react";
import { api, SHOWCASE, useRun } from "./api";
import type { RunView } from "./contracts";
import { AssessmentCard, Icon, LiveStatus, Loading, Mark, ProofPanel, ReadinessBadge, RunDot, SampleBadge, StatusIcon, STEPS, tone } from "./components";
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
import { Modal, ToastProvider } from "./ui";
import { Item, spring, Stagger } from "./motion";

const NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/my-runs", label: "My runs" },
  { to: "/explore", label: "Explore a repo" },
  { to: "/eval", label: "Accuracy" },
] as const;

function NavLinks({ waiting, feedback, id }: { waiting: number; feedback: number; id: string }) {
  return (
    <ul className="flex flex-col md:flex-row gap-1 list-none p-0">
      {NAV.map((n) => (
        <li key={n.to}>
          <NavLink to={n.to} end={"end" in n} className={({ isActive }) => `relative flex items-center gap-2 h-11 md:h-10 px-4 rounded-full no-underline font-semibold text-[14.5px] transition-colors ${isActive ? "text-ink" : "text-muted hover:text-ink"}`}>
            {({ isActive }) => (<>
              {isActive && <motion.span layoutId={id} className="absolute inset-0 rounded-full bg-white" transition={spring} aria-hidden />}
              <span className="relative">{n.label}</span>
              {n.to === "/my-runs" && waiting > 0 && <span className="relative grid place-items-center min-w-5 h-5 px-1.5 rounded-full bg-peach-300 text-[11.5px] font-bold" aria-label={`${waiting} waiting for your approval`}>{waiting}</span>}
              {n.to === "/my-runs" && feedback > 0 && <span className="relative inline-flex items-center gap-1 h-5 px-1.5 rounded-full bg-butter-100 text-butter-700 text-[11.5px] font-bold" title="New maintainer feedback on GitHub" aria-label={`${feedback} with new maintainer feedback`}><Icon name="message" size={12} />{feedback}</span>}
            </>)}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<{ signed_in: boolean; login: string | null } | null>(null);
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const mine = useMyRuns();
  const waiting = mine.items?.filter((i) => i.status === "awaiting_approval").length ?? 0;   // a count only on a queue that needs you
  const feedback = mine.items?.filter((i) => i.new_feedback > 0).length ?? 0;   // set by the worker's 10-min PR poll
  useEffect(() => { api<{ signed_in: boolean; login: string | null }>("/api/me").then(setMe).catch(() => setMe(null)); }, []);
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {   // Escape closes the phone menu
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  const signOut = () => fetch("/auth/logout", { method: "POST" }).finally(() => window.location.assign("/"));
  const account = me?.signed_in
    ? <span className="flex items-center gap-2 font-semibold text-[14px]"><span className="grid place-items-center w-8 h-8 rounded-full bg-lav-100 text-lav-700 text-[13px]" aria-hidden>{(me.login ?? "?")[0].toUpperCase()}</span>{me.login}
        <button className="secondary-btn !min-h-9 !px-3 text-[13px]" onClick={signOut}>Sign out</button></span>
    : <Link to="/connect" className="button secondary !min-h-10"><Icon name="github" />Sign in with GitHub</Link>;
  return (
    <div className="min-h-dvh flex flex-col">
      <header className="sticky top-0 z-40 bg-ground">
        <div className="max-w-[1180px] mx-auto px-5 md:px-8 h-[72px] flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2.5 no-underline font-display font-bold text-[21px] tracking-tight text-ink hover:text-ink" aria-label="PatchPilot home">
            <motion.span whileHover={{ rotate: 18, scale: 1.08 }} transition={spring} className="grid"><Mark /></motion.span>PatchPilot
          </Link>
          <nav aria-label="Main" className="hidden md:block"><NavLinks waiting={waiting} feedback={feedback} id="nav-desk" /></nav>
          <div className="ml-auto hidden md:block">{account}</div>
          <button className="secondary md:!hidden ml-auto" aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}>
            <Icon name={open ? "x" : "menu"} />{open ? "Close" : "Menu"}
          </button>
        </div>
        <AnimatePresence>
          {open && (
            <motion.nav id="mobile-nav" aria-label="Main" className="md:hidden mx-4 mb-3 p-3 rounded-[24px] bg-soft"
              initial={{ opacity: 0, y: -10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }} transition={spring}>
              <NavLinks waiting={waiting} feedback={feedback} id="nav-phone" />
              <div className="px-2 pt-3">{account}</div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>
      <motion.main key={loc.pathname} className="w-full max-w-[1180px] mx-auto px-5 md:px-8 pt-6 pb-24 flex-1"
        initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>
        {children}
      </motion.main>
      <footer className="max-w-[1180px] w-full mx-auto px-5 md:px-8 pb-8 flex flex-wrap items-center justify-between gap-3 text-[13px] text-muted">
        <span className="flex items-center gap-2"><Mark size={20} />PatchPilot fixes bugs with proof, and publishes only what you approve.</span>
        <span className="flex items-center gap-2">
          <span className="relative flex w-2 h-2"><span className="absolute inset-0 rounded-full bg-mint-500 animate-ping opacity-60" /><span className="relative w-2 h-2 rounded-full bg-mint-500" /></span>
          {SHOWCASE ? "Showcase: recorded runs, read-only." : "Live on a demo machine. Runs stop if it goes offline."}
        </span>
      </footer>
    </div>
  );
}

// A real, planted bug in the team's demo repo: one click shows the whole flow on an issue PatchPilot is known to fix.
const TRY = "https://github.com/Niranjan-cyber/tinycalc/issues/1";
const HOW = [
  ["search", "Check the issue", "Is it a clear bug in a Python project with tests, and has nobody fixed it yet?", "bg-lav-50", "text-lav-700"],
  ["flask", "Reproduce it", "A new test fails twice on the original code, in a sandbox with no network.", "bg-rose-50", "text-rose-700"],
  ["check", "Fix and verify", "The same test passes twice in a fresh sandbox, and old tests still pass.", "bg-mint-50", "text-mint-700"],
  ["eye", "You decide", "You read the exact change and approve it. Nothing reaches GitHub before that.", "bg-peach-50", "text-peach-700"],
] as const;
const ISSUE_RE = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/issues\/\d+\/?$/;
/** Accepts a full issue URL or owner/repo#123. */
const normalise = (s: string) => {
  const t = s.trim(); const m = /^([\w.-]+)\/([\w.-]+)#(\d+)$/.exec(t);
  return m ? `https://github.com/${m[1]}/${m[2]}/issues/${m[3]}` : t;
};
const runWord = (i: { status: string; readiness?: string | null }) => i.status === "awaiting_approval" ? "Needs your approval"
  : i.readiness ?? (i.status === "queued" ? "Waiting to start" : i.status === "paused" ? "Paused" : "Running");

/** The home page's live thing: a recorded example run replaying its red-to-green proof every few seconds. */
function DemoCard() {
  const [run, setRun] = useState<RunView | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => { api<RunView>("/api/runs/verified_fix").then(setRun).catch(() => setRun(null)); }, []);
  useEffect(() => { const t = setInterval(() => setTick((n) => n + 1), 7000); return () => clearInterval(t); }, []);
  if (!run?.repro) return null;
  const after = run.verify?.new_test_runs ?? [];
  return (
    <motion.div className="relative" initial={{ opacity: 0, y: 30, rotate: 0 }} animate={{ opacity: 1, y: 0, rotate: -1.5 }}
      whileHover={{ rotate: 0, y: -4 }} transition={{ ...spring, delay: 0.25 }}>
      <div className="bg-white rounded-[32px] p-6 md:p-7 shadow-[var(--shadow-float)]">
        <div className="flex items-center justify-between gap-3 mb-3">
          <span className="text-[13px] text-muted truncate">{run.issue.repo} #{run.issue.number}</span><SampleBadge />
        </div>
        <p className="font-display font-semibold text-[20px] leading-snug !mb-5">{run.issue.title}</p>
        <div key={tick} className="grid gap-3">
          <div className="rounded-[20px] bg-rose-50 p-4">
            <p className="text-[13px] font-semibold text-rose-700 !mb-2.5">Before the fix</p>
            <div className="flex flex-wrap gap-2">{(run.repro.runs_on_base ?? []).map((s, i) => <RunDot key={i} s={s} i={i} delay={0.3} />)}</div>
          </div>
          <div className="rounded-[20px] bg-mint-50 p-4">
            <p className="text-[13px] font-semibold text-mint-700 !mb-2.5">After the fix, fresh sandbox</p>
            <div className="flex flex-wrap gap-2">{after.map((s, i) => <RunDot key={i} s={s} i={i} delay={0.9} />)}</div>
          </div>
          <div className="flex items-center gap-1 pt-1" aria-label="All 8 steps recorded">
            {STEPS.map((st, i) => (
              <motion.span key={st.id} title={st.label} className="h-1.5 flex-1 rounded-full bg-mint-300 origin-left"
                initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 1.3 + i * 0.08, duration: 0.35 }} />
            ))}
          </div>
        </div>
        <Link to="/runs/verified_fix" className="mt-5 inline-flex items-center gap-1.5 font-semibold text-[14px] no-underline text-peach-700 group">
          Open this example<span className="transition-transform group-hover:translate-x-1"><Icon name="arrow" /></span>
        </Link>
      </div>
    </motion.div>
  );
}

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
  // the runs waiting on you first, then the newest; five at most
  const recent = [...items.filter((i) => i.status === "awaiting_approval"), ...items.filter((i) => i.status !== "awaiting_approval")].slice(0, 5);
  return (
    <div className="start flex flex-col gap-20 md:gap-24">
      <section className="grid grid-cols-1 [&>*]:min-w-0 lg:grid-cols-[1.15fr_0.85fr] gap-12 lg:gap-16 items-center pt-6 md:pt-14">
        <Stagger className="launch">
          <Item as="div"><h1 className="!text-[44px] md:!text-[64px] !leading-[1.0] !tracking-[-0.035em] !font-extrabold max-w-[12ch]">Fix your first bug, with proof.</h1></Item>
          <Item as="div"><p className="lede !mt-6">Paste a GitHub issue. PatchPilot reproduces the bug, tests a fix against it, and shows you the proof. Nothing reaches GitHub until you approve it.</p></Item>
          <Item as="div">
            <form noValidate onSubmit={(e) => { e.preventDefault(); setTouched(true); if (ISSUE_RE.test(target)) check(target); }} className="paste mt-8 max-w-[600px]">
              <label htmlFor="issue" className="font-semibold text-[14px] mb-2">GitHub issue link</label>
              <div className={`flex items-center gap-2 p-2 pl-5 rounded-full bg-white transition-shadow focus-within:shadow-[0_0_0_3px_var(--color-peach-300)] ${bad ? "shadow-[0_0_0_2px_var(--color-rose-300)]" : ""}`}>
                <Icon name="github" size={18} />
                <input id="issue" ref={input} value={url} onChange={(e) => setUrl(e.target.value)} onBlur={() => setTouched(true)} placeholder="github.com/owner/repo/issues/123"
                  aria-invalid={bad} aria-describedby="issue-hint" autoComplete="off" spellCheck={false}
                  className="!m-0 !bg-transparent !border-0 !rounded-none !px-1 !py-2 flex-1 min-w-0 !shadow-none focus:!bg-transparent" />
                <motion.button type="submit" whileTap={{ scale: 0.95 }} className="!min-h-12 !px-6">Check issue<Icon name="arrow" /></motion.button>
              </div>
              {bad ? <p className="field-error pl-5" id="issue-hint" role="alert">That isn't a GitHub issue link. It should look like github.com/owner/repo/issues/123.</p>
                : <p className="hint pl-5 !mt-3" id="issue-hint">Works on public Python projects with pytest tests. Other issues get an assessment instead of a fix.</p>}
            </form>
          </Item>
          <Item as="div"><p className="try mt-6 flex flex-wrap items-center gap-3 text-muted">No issue in mind?
            <button type="button" className="secondary !min-h-10" onClick={() => check(TRY)}><Icon name="flask" />Try a sample bug</button></p></Item>
        </Stagger>
        <DemoCard />
      </section>

      <section aria-labelledby="how-h">
        <h2 id="how-h" className="!text-[30px] !mb-6">How it works</h2>
        <ol className="how grid sm:grid-cols-2 lg:grid-cols-4 gap-3 list-none p-0">
          {HOW.map(([i, t, d, bg, fg], n) => (
            <motion.li key={t} className={`${bg} rounded-[var(--radius-card)] p-6 flex flex-col gap-2`}
              initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }}
              whileHover={{ y: -6 }} transition={{ ...spring, delay: n * 0.08 }}>
              <span className={`${fg} mb-6`}><Icon name={i} size={30} /></span>
              <strong className="font-display text-[19px] leading-tight">{t}</strong>
              <span className="text-[14.5px] text-muted">{d}</span>
            </motion.li>
          ))}
        </ol>
      </section>

      {items.length > 0 && (
        <section aria-labelledby="runs-h">
          <div className="flex items-baseline justify-between gap-3 mb-5"><h2 id="runs-h" className="!text-[30px] !m-0">Your runs</h2><Link to="/my-runs" className="font-semibold">View all</Link></div>
          <ul className="runlist">{recent.map((i) => (
            <li key={i.run_id}>
              <Link to={`/runs/${i.run_id}`}><strong>{i.title}</strong></Link>
              <span className="hint">{i.repo}#{i.number} · {new Date(i.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</span>
              <span className={`pill pill-${i.status}`}>{runWord(i)}</span>
            </li>))}</ul>
        </section>
      )}

      {fixtures.length > 0 && (
        <details className="samples group bg-white rounded-[var(--radius-card)] p-6 md:p-7">
          <summary className="flex items-center gap-3 list-none font-display font-semibold text-[21px] [&::-webkit-details-marker]:hidden">
            <span className="grid place-items-center w-9 h-9 rounded-full bg-soft transition-transform duration-300 group-open:rotate-90"><Icon name="chev" /></span>
            See every way a run can end <SampleBadge />
          </summary>
          <p className="hint !mt-3">Recorded runs, including the ones that don't produce a fix.</p>
          <ul className="sample-grid grid sm:grid-cols-2 lg:grid-cols-3 gap-2 list-none p-0 mt-4">{fixtures.map((f) => (
            <li key={f}><Link to={`/runs/${f}`} className="flex items-center justify-between gap-2 px-4 py-3 rounded-2xl bg-ground no-underline font-medium text-[14px] transition-colors hover:bg-peach-50">
              {f[0].toUpperCase() + f.slice(1).replaceAll("_", " ")}<Icon name="chev" size={14} /></Link></li>))}</ul>
        </details>
      )}
    </div>
  );
}

const OUTCOME_TEXT: Record<string, string> = {
  CANNOT_REPRODUCE: "We couldn't make the bug happen in a test, so there's no fix to prove. The report says what we tried.",
  ENV_FAILED: "We couldn't install this project in the sandbox, so none of its code ran. The report has the install log.",
  BLOCKED: "A dependency looked malicious, so nothing from this repository was installed or run.",
  STOPPED: "This run was stopped. Everything recorded up to that point is kept.",
  SYSTEM_ERROR: "Something on our side failed. The report has what we know; nothing was published.",
  ASSESSMENT_ONLY: "Nothing ran: this issue got an assessment instead of a fix attempt. Details are below.",
};
// the decision block's tint and its big status disc, by tone (components.tone)
const TONE: Record<string, [string, string, string]> = {
  act: ["bg-peach-100", "bg-peach-300 text-ink", "eye"], good: ["bg-mint-50", "bg-mint-500 text-white", "check"],
  warn: ["bg-butter-50", "bg-butter-300 text-ink", "alert"], bad: ["bg-rose-50", "bg-rose-500 text-white", "x"],
  muted: ["bg-white", "bg-soft text-muted", "dash"], work: ["bg-lav-50", "bg-lav-500 text-white", "activity"],
};

function Run() {
  const { id = "" } = useParams();
  const { run, events, error } = useRun(id);
  const [confirmStop, setConfirmStop] = useState(false);
  if (error) return <section className="panel failed max-w-[720px]"><h1>Couldn't load this run</h1><p>{error.message}</p><Link className="button" to="/">Back to home</Link></section>;
  if (!run) return <Loading label="Loading the run…" />;
  const done = !!run.outcome;
  const real = /^[0-9a-f-]{36}$/.test(id);
  const assessed = run.outcome === "ASSESSMENT_ONLY";   // nothing ran: the assessment is the whole report
  const next = run.pr ? { to: `/runs/${id}/pr`, t: "A draft pull request is open", d: "See it on GitHub and what happens next.", b: "See the pull request" }
    : run.status === "awaiting_approval" && run.approval ? { to: `/connect?run=${id}`, t: "Approved. Ready to publish", d: "Connect GitHub to open a draft pull request with exactly this change.", b: "Publish draft pull request" }
    : run.status === "awaiting_approval" ? { to: `/runs/${id}/review`, t: "Your turn: review the change", d: "The fix passed in a fresh sandbox. Read the exact change and approve it; nothing is published until you do.", b: "Review and approve" } : null;
  const concerns = (run.review as { concerns?: unknown[] } | null | undefined)?.concerns?.length ?? 0;
  const hv = run.verify?.hidden_variant;
  const extraRan = hv === "passed" || hv === "failed";   // otherwise the extra checks are all "not run" and wait under More details
  const [bg, disc, glyph] = TONE[next ? "act" : tone(run)];
  return (
    <div className="run-page">
      <RunHeader run={run} id={id} badge={false} />
      {/* wide screens: what you act on at the left, where the run is and its facts in a rail that stays in view */}
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-12 items-start">
      <Stagger className="flex flex-col gap-10 min-w-0">
        <div className="flex flex-col gap-3 empty:hidden">
          <GuidedPauseNotice run={run} />
          {run.status === "paused" && run.pause?.reason !== "guided_pause" && (
            <p className="notice warn">
              {run.pause?.resume_at ? `Paused: free AI capacity resumes around ${new Date(run.pause.resume_at).toLocaleTimeString()}.`
                : "Paused until free AI capacity is available. We'll stop and keep your report if that takes over 2 hours."}
            </p>
          )}
          {run.supplyguard?.status === "inconclusive" && <p className="notice warn">We couldn't fully check this project's dependencies, so publishing is turned off.</p>}
          {run.details_expired_at && <p className="notice">This run's details have expired. The outcome and pull request link are kept.</p>}
        </div>

        <Item as="section" className={`decision${next ? " act" : ""} ${bg} rounded-[28px] p-6 md:p-8 flex gap-6 items-start`} aria-label="Where this run stands">
          <div className="flex-1 min-w-0">
            <ReadinessBadge run={run} />
            {done ? (
              <>
                <h2 className="!text-[24px] md:!text-[28px] !mt-3 !mb-2">{next?.t ?? (OUTCOME_TEXT[run.outcome!] ? "What happened" : "Read the report")}</h2>
                <p className="text-[16px] max-w-[56ch]">{next?.d ?? OUTCOME_TEXT[run.outcome!] ?? "PatchPilot found something a person needs to look at. The report has everything it recorded."}</p>
                <div className="row !mt-5">
                  {next && <Link className="button !min-h-12 !px-6" to={next.to}>{next.b}<Icon name="arrow" /></Link>}
                  <a className={`button ${next ? "secondary !bg-white/70 hover:!bg-white" : "!bg-white hover:!bg-white/70"}`} href={`/api/runs/${id}/report.md`}><Icon name="file" />Download report</a>
                </div>
              </>
            ) : (
              <div className="mt-4">
                <LiveStatus run={run} />
                {real && <div className="row"><button className="danger-btn !bg-white/70" onClick={() => setConfirmStop(true)}><Icon name="stop" />Stop run</button></div>}
              </div>
            )}
          </div>
          <motion.span aria-hidden className={`hidden sm:grid place-items-center shrink-0 w-16 h-16 rounded-full ${disc}`}
            initial={{ scale: 0, rotate: -40 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 300, damping: 16, delay: 0.2 }}>
            {done ? <Icon name={glyph} size={28} /> : <StatusIcon s={run.status === "paused" ? "inconclusive" : "running"} size={28} />}
          </motion.span>
        </Item>

        {done && !!run.repro?.runs_on_base?.length && (
          <Item as="section" aria-labelledby="proof-h">
            <h2 id="proof-h">Proof</h2>
            <ProofPanel run={run} />
          </Item>
        )}
        {assessed && <Item><AssessmentCard a={run.assessment} /></Item>}
        <Item className="empty:hidden"><DiagnosisCard run={run} /></Item>
        {concerns > 0 && <Item><Findings run={run} /></Item>}
        <Item className="empty:hidden"><AttemptHistory events={events} /></Item>
        {extraRan && <Item><ExtraChecks run={run} /></Item>}
        <Item className="empty:hidden"><AskPanel run={run} /></Item>
        <Item className="empty:hidden"><PauseToggles run={run} /></Item>

        {!extraRan && (
          <Item as="div">
            <details className="more group">
              <summary className="inline-flex items-center gap-2 font-semibold text-muted hover:text-ink list-none [&::-webkit-details-marker]:hidden">
                <span className="grid place-items-center w-8 h-8 rounded-full bg-white transition-transform duration-300 group-open:rotate-90"><Icon name="chev" size={14} /></span>More details
              </summary>
              <div className="more-body grid gap-4 mt-4"><ExtraChecks run={run} /></div>
            </details>
          </Item>
        )}
      </Stagger>
      <aside className="run-rail flex flex-col gap-6 min-w-0 lg:sticky lg:top-[88px]" aria-label="This run">
        {!assessed && (
          <section aria-labelledby="steps-h">
            <h2 id="steps-h" className="!text-[18px] !mb-3">What PatchPilot did</h2>
            <StageNavigator run={run} />
          </section>
        )}
        <RunDetails run={run} />
        <div><ActivityButton events={events} /></div>
      </aside>
      </div>

      <Modal open={confirmStop} onClose={() => setConfirmStop(false)} title="Stop this run?"
        actions={<>
          <button className="secondary" onClick={() => setConfirmStop(false)}>Keep running</button>
          <button className="danger-solid" onClick={() => { setConfirmStop(false); api(`/api/runs/${id}/stop`, { method: "POST" }).catch(() => null); }}>Stop run</button>
        </>}>
        <p>The run ends where it is and keeps its report so far. A stopped run can never be published; you'd start a new run to try again.</p>
      </Modal>
    </div>
  );
}

const Stub = ({ title, children }: { title: string; children?: React.ReactNode }) => (
  <section className="panel empty max-w-[640px] mx-auto mt-10"><h1 className="!mb-3">{title}</h1>{children}</section>
);

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
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
              <div className="row"><Link className="button" to="/">Back to home</Link><Link className="button secondary" to="/my-runs">My runs</Link></div></Stub>} />
          </Routes>
        </Shell>
      </ToastProvider>
    </MotionConfig>
  );
}
