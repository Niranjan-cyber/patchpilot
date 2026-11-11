import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import { Icon, Loading, StatusIcon } from "./components";
import { api, ApiError } from "./api";
import { spring } from "./motion";
import { CI, FeedbackBadge, GH, ProgressSummary, RUNS_CHANGED, useProgress, type Row } from "./Progress";

type Item = { run_id: string; title: string; repo: string; number: number; status: string; outcome: string | null;
  readiness: string | null; created_at: string; pr_url: string | null; new_feedback: number };

export function useMyRuns() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const load = () => api<Item[]>("/api/me/runs").then(setItems).catch(setErr);
  useEffect(() => {
    load();
    // the badge is an alert: re-read the stored counts (no GitHub call) every 2 min while visible, and on focus
    const tick = () => { if (document.visibilityState === "visible") load(); };
    const t = window.setInterval(tick, 120_000);
    window.addEventListener(RUNS_CHANGED, load);
    window.addEventListener("focus", tick);
    return () => { window.clearInterval(t); window.removeEventListener(RUNS_CHANGED, load); window.removeEventListener("focus", tick); };
  }, []);
  return { items, err, load };
}

const ACTIVE = new Set(["queued", "running", "paused", "interrupted", "revising", "publishing"]);
type Lane = "needs" | "active" | "done";
// a run needs you when its approval waits, or GitHub has something new or failing on its PR
const lane = (i: Item, g?: Row): Lane =>
  i.status === "awaiting_approval" || i.new_feedback > 0 || g?.needs_attention ? "needs" : ACTIVE.has(i.status) ? "active" : "done";

// the one status mark per row: icon + word, tinted by what it asks of you
function state(i: Item): [string, string, string] {
  if (i.status === "awaiting_approval") return ["pill-awaiting_approval", "eye", "Needs your approval"];
  if (i.status === "paused") return ["pill-paused", "pause", "Paused"];
  if (ACTIVE.has(i.status)) return ["pill-running", "activity", i.status === "queued" ? "Waiting to start" : i.status === "publishing" ? "Publishing" : "Running"];
  if (i.status === "published") return ["pill-pass", "check", i.pr_url ? "PR opened" : "Branch pushed"];
  const k = i.outcome === "VERIFIED_FIX" ? ["pill-pass", "check"] : i.outcome === "FIX_NEEDS_ATTENTION" ? ["pill-paused", "alert"]
    : i.outcome === "ASSESSMENT_ONLY" || i.outcome === "STOPPED" ? ["pill-muted", "dash"] : ["pill-fail", "x"];
  return [k[0], k[1], i.readiness ?? "Finished"];
}

const DAY = 86_400_000;
function ago(iso: string) {
  const d = new Date(iso), s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < DAY / 1000) return `${Math.floor(s / 3600)} h ago`;
  if (s < 2 * DAY / 1000) return "yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}
function dayGroup(iso: string) {
  const start = new Date(); start.setHours(0, 0, 0, 0);
  const t = new Date(iso).getTime();
  return t >= start.getTime() ? "Today" : t >= start.getTime() - DAY ? "Yesterday" : t >= start.getTime() - 6 * DAY ? "Earlier this week" : "Older";
}

function GitHubCell({ i, g }: { i: Item; g?: Row }) {
  if (!i.pr_url && !g?.patchpilot.compare_url) return <span className="text-faint">No pull request</span>;
  if (!i.pr_url) return <a href={g!.patchpilot.compare_url!}>Branch pushed</a>;
  const s = g?.github_pr_status;
  return (
    <span className="flex flex-col items-end leading-tight">
      <a href={i.pr_url} className={s ? `gh-${s}` : ""}>{s ? GH[s] : g ? "Status unavailable" : "Pull request"}</a>
      {g?.ci && <span className={`ci ci-${g.ci} text-[12.5px]`}>{CI[g.ci]}</span>}
    </span>
  );
}

function RunRow({ i, g, onForget, older, open, onToggle }: { i: Item; g?: Row; onForget?: (id: string) => void;
  older?: number; open?: boolean; onToggle?: () => void }) {
  const [pill, icon, word] = state(i);
  return (
    <li className={`runrow ${older === undefined ? "runrow-older" : ""}`}>
      <span className={`pill ${pill}`}><Icon name={icon} size={13} />{word}</span>
      <div className="min-w-0">
        <Link to={`/runs/${i.run_id}`} className="runrow-title">{i.title}</Link>
        <span className="runrow-sub">{i.repo} #{i.number} · <time dateTime={i.created_at} title={new Date(i.created_at).toLocaleString()}>{ago(i.created_at)}</time>
          {!!older && <> · <button className="runrow-earlier" aria-expanded={open} onClick={onToggle}>
            {open ? "Hide " : "+"}{older} earlier run{older === 1 ? "" : "s"}</button></>}</span>
      </div>
      <div className="runrow-gh">
        <FeedbackBadge runId={i.run_id} n={g?.new_feedback ?? i.new_feedback} />
        <GitHubCell i={i} g={g} />
      </div>
      {onForget && <button className="runrow-forget" onClick={() => onForget(i.run_id)} aria-label={`Forget this run: ${i.title}`} title="Forget this run">
        <Icon name="x" size={14} /></button>}
    </li>
  );
}

/** One issue: its newest run, with the earlier runs of the same issue folded under it. */
function IssueRuns({ runs, gh, onForget }: { runs: Item[]; gh: Map<string, Row>; onForget: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [first, ...rest] = runs;
  return <>
    <RunRow i={first} g={gh.get(first.run_id)} onForget={onForget} older={rest.length} open={open} onToggle={() => setOpen(!open)} />
    {open && rest.map((i) => <RunRow key={i.run_id} i={i} g={gh.get(i.run_id)} onForget={onForget} />)}
  </>;
}

/** One repository or day: its newest issues first, five at a time. */
function Group({ name, items, gh, onForget, open, repo }: { name: string; items: Item[]; gh: Map<string, Row>; onForget: (id: string) => void; open: boolean; repo: boolean }) {
  const [all, setAll] = useState(false);
  const issues = useMemo(() => {
    const m = new Map<string, Item[]>();
    for (const i of items) { const k = `${i.repo}#${i.number}`; m.set(k, [...(m.get(k) ?? []), i]); }
    return [...m.values()];
  }, [items]);
  const shown = all || open ? issues : issues.slice(0, 5);
  const waiting = items.filter((i) => i.status === "awaiting_approval").length;
  return (
    <section className="rungroup" aria-label={name}>
      <header>
        <h3>{repo ? <a href={`https://github.com/${name}`}><Icon name="github" size={15} />{name}</a> : name}</h3>
        <span className="text-faint text-[13px]">{issues.length} issue{issues.length === 1 ? "" : "s"}{items.length > issues.length ? `, ${items.length} runs` : ""}
          {waiting ? ` · ${waiting} waiting for you` : ""}</span>
      </header>
      <ul>{shown.map((r) => <IssueRuns key={r[0].run_id} runs={r} gh={gh} onForget={onForget} />)}</ul>
      {shown.length < issues.length && <button className="rungroup-more" onClick={() => setAll(true)}>Show all {issues.length} issues<Icon name="chev" size={13} /></button>}
    </section>
  );
}

const LANES: [Lane | "all", string][] = [["needs", "Needs you"], ["active", "In progress"], ["done", "Finished"], ["all", "All"]];

export default function MyRuns() {
  const { items, err, load } = useMyRuns();
  const progress = useProgress();
  const [params, setParams] = useSearchParams();
  const set = (k: string, v: string | null) => setParams((p) => { if (v) p.set(k, v); else p.delete(k); return p; }, { replace: true });
  const q = params.get("q") ?? "";
  const by = params.get("group") === "date" ? "date" : "repo";
  const forget = (id: string) => api(`/api/runs/${id}/access`, { method: "DELETE" }).catch(() => null).then(load);

  const gh = useMemo(() => new Map((progress.p?.rows ?? []).map((r) => [r.run_id, r])), [progress.p]);
  const lanes = useMemo(() => {
    const out: Record<Lane | "all", Item[]> = { needs: [], active: [], done: [], all: items ?? [] };
    for (const i of items ?? []) out[lane(i, gh.get(i.run_id))].push(i);
    return out;
  }, [items, gh]);
  // open on what needs you when anything does; an explicit choice in the URL wins
  const view = (params.get("view") as Lane | "all" | null) ?? (lanes.needs.length ? "needs" : "all");
  const needle = q.trim().toLowerCase();
  const list = lanes[view].filter((i) => !needle || `${i.title} ${i.repo} #${i.number} ${i.repo}#${i.number}`.toLowerCase().includes(needle));
  const groups = useMemo(() => {
    const m = new Map<string, Item[]>();
    for (const i of list) { const k = by === "repo" ? i.repo : dayGroup(i.created_at); m.set(k, [...(m.get(k) ?? []), i]); }
    // repositories: the one with the newest run first (the list is already newest first)
    return [...m.entries()];
  }, [list, by]);

  if (err) return <section className="panel failed"><h1>Couldn't load your runs</h1><p>{err.message}</p><button onClick={load}>Try again</button></section>;
  if (!items) return <Loading label="Loading your runs…" />;
  const repos = new Set(items.map((i) => i.repo)).size;
  return (
    <section className="myruns">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="!mb-1">My runs</h1>
          <p className="hint !m-0">{items.length ? `${items.length} run${items.length === 1 ? "" : "s"} across ${repos} repositor${repos === 1 ? "y" : "ies"}. ` : ""}
            They open only in this browser; sign in with GitHub to see them on other devices.</p>
        </div>
        <Link className="button" to="/"><Icon name="plus" />New run</Link>
      </div>

      {items.length ? <>
        <ProgressSummary p={progress.p} err={progress.err} reload={progress.load} />

        <div className="runs-toolbar">
          <nav className="lanes inline-flex gap-1 p-1 rounded-full bg-soft max-w-full overflow-x-auto" aria-label="Filter runs">
            {LANES.map(([k, label]) => (
              <button key={k} className={`lane ${view === k ? "text-ink" : "text-muted hover:text-ink"}`} aria-pressed={view === k} onClick={() => set("view", k)}>
                {view === k && <motion.span layoutId="lane-pill" className="absolute inset-0 rounded-full bg-white" transition={spring} aria-hidden />}
                <span className="relative">{label}</span>
                <span className={`relative lane-n ${k === "needs" && lanes.needs.length ? "lane-n-act" : ""}`}>{lanes[k].length}</span>
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-2 ml-auto">
            <label className="runs-search"><Icon name="search" size={15} /><span className="sr-only">Search runs</span>
              <input type="search" value={q} onChange={(e) => set("q", e.target.value || null)} placeholder="Search repo, issue or title" /></label>
            <div className="inline-flex p-1 rounded-full bg-soft" role="group" aria-label="Group by">
              {(["repo", "date"] as const).map((k) => (
                <button key={k} className={`groupby ${by === k ? "bg-white text-ink" : "text-muted hover:text-ink"}`} aria-pressed={by === k}
                  onClick={() => set("group", k === "repo" ? null : k)}>{k === "repo" ? "Repository" : "Date"}</button>
              ))}
            </div>
          </div>
        </div>

        {groups.length ? (
          <div className="rungroups">
            {groups.map(([name, rows]) => <Group key={`${by}-${view}-${name}`} name={name} items={rows} gh={gh} onForget={forget} open={!!needle} repo={by === "repo"} />)}
          </div>
        ) : (
          <div className="panel empty flex items-start gap-4">
            <span className="text-mint-700 mt-1"><StatusIcon s={needle ? "not_run" : "passed"} size={20} /></span>
            <div>{needle ? <><h2>No runs match "{q}"</h2><p>Search looks at the repository, the issue number and the title. <button className="linklike" onClick={() => set("q", null)}>Clear the search</button></p></>
              : view === "needs" ? <><h2>Nothing needs you right now</h2><p>No approvals waiting, no new maintainer feedback and no failing CI on your pull requests.</p></>
              : view === "active" ? <><h2>Nothing is running</h2><p>Runs you start show up here while they work. <Link to="/">Start a new run</Link></p></>
              : <><h2>No finished runs yet</h2><p>A run lands here when it ends, with its proof and report.</p></>}</div>
          </div>
        )}
      </> : (
        <div className="panel empty"><h2>No runs yet. Paste an issue to start.</h2>
          <p>Each run you start in this browser shows up here, with its proof and report.</p><Link className="button" to="/">New run</Link></div>
      )}
    </section>
  );
}
