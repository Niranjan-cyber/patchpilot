import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { RUNS_CHANGED } from "./Progress";

type Item = { id: string; source: "review" | "comment" | "ci"; author: string | null; at: string | null; url: string | null;
  quote: string; path: string | null; line: number | null; new: boolean; category: string | null; label: string;
  meaning: string | null; why: string | null; reply: string | null; change: string | null; needs_judgement: boolean | null };
type Assist = { state: "ok" | "empty" | "no_pr" | "unavailable"; items: Item[]; model_ok: boolean | null; plan: string[] | null };

const tone = (i: Item) => i.category === "ci" ? "badge-bad" : i.category === "non_actionable" ? "" : i.category ? "badge-warn" : "";

function Request({ i, picked, toggle }: { i: Item; picked: boolean; toggle: () => void }) {
  return (
    <li className={`fb-item${i.new ? " is-new" : ""}`}>
      <div className="fb-head">
        <span className={`badge ${tone(i)}`}>{i.label}</span>
        <span>{i.author ?? "GitHub Actions"}{i.at && <span className="hint">, {new Date(i.at).toLocaleString()}</span>}</span>
        {i.new && <strong className="new-tag">New</strong>}
        {i.needs_judgement && <span className="badge badge-warn">Needs your judgement</span>}
        {i.url && <a href={i.url}>Open on GitHub</a>}
      </div>
      {i.path && <p className="hint"><code>{i.path}{i.line ? `:${i.line}` : ""}</code></p>}
      <blockquote className="fb-quote">{i.quote || <span className="hint">(no text)</span>}</blockquote>
      {i.meaning ? <dl className="fb-explain">
        <dt>What it means</dt><dd>{i.meaning}</dd>
        {i.why && <><dt>Why it matters</dt><dd>{i.why}</dd></>}
        {i.change && <><dt>Proposed change</dt><dd><pre>{i.change}</pre></dd></>}
        {i.reply && <><dt>Draft reply <span className="hint">(not posted; copy it if you want it)</span></dt><dd>{i.reply}</dd></>}
      </dl> : i.category !== "non_actionable" && <p className="hint">Not classified: the model wasn't available, so read the comment yourself.</p>}
      {i.category !== "non_actionable" && (
        <label className="fb-pick"><input type="checkbox" checked={picked} onChange={toggle} /> Include in the revision plan</label>
      )}
    </li>
  );
}

/** #102: maintainer feedback explained, read-only. Nothing here posts, pushes or dismisses on GitHub. */
export default function FeedbackAssistant({ id }: { id: string }) {
  const [a, setA] = useState<Assist | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const load = () => {
    setErr(null);
    api<Assist>(`/api/runs/${id}/feedback/assist`).then((x) => {
      setA(x); setPicked(new Set(x.plan ?? []));
      return api(`/api/runs/${id}/feedback/seen`, { method: "POST" });
    }).then(() => window.dispatchEvent(new Event(RUNS_CHANGED))).catch(setErr);
  };
  useEffect(load, [id]);
  if (err) return <div className="notice warn"><p>Couldn't load the feedback: {err.message}</p><button className="linklike" onClick={load}>Try again</button></div>;
  if (!a) return <p className="hint" aria-busy="true">Reading the pull request on GitHub…</p>;
  if (a.state === "unavailable") return <p className="notice warn">GitHub didn't answer, so the feedback is unavailable right now. <button className="linklike" onClick={load}>Check again</button></p>;
  if (a.state !== "ok") return <p className="hint">No maintainer feedback yet. We check every 10 minutes and flag anything new in My runs.</p>;
  const act = a.items.filter((i) => i.category !== "non_actionable");
  const rest = a.items.filter((i) => i.category === "non_actionable");
  const toggle = (k: string) => { const s = new Set(picked); s.has(k) ? s.delete(k) : s.add(k); setPicked(s); setSaved(null); };
  const save = () => {
    setSaving(true);
    api<{ evidence_id: string }>(`/api/runs/${id}/feedback/plan`, { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_ids: [...picked] }) }).then(() => setSaved(`Saved ${picked.size} request${picked.size > 1 ? "s" : ""}.`))
      .catch((e: ApiError) => setSaved(e.message)).finally(() => setSaving(false));
  };
  return (
    <div className="fb">
      {a.model_ok === false && <p className="notice warn">The model wasn't available, so some items are "Not classified". The comments themselves are shown as written.</p>}
      {act.length ? <ul className="fb-list">{act.map((i) => <Request key={i.id} i={i} picked={picked.has(i.id)} toggle={() => toggle(i.id)} />)}</ul>
        : <p className="hint">Nothing to change: the feedback so far is thanks, approvals or notes.</p>}
      {!!rest.length && <details className="fb-rest"><summary>{rest.length} comment{rest.length > 1 ? "s" : ""} with nothing to change</summary>
        <ul className="fb-list">{rest.map((i) => <Request key={i.id} i={i} picked={false} toggle={() => null} />)}</ul></details>}
      {!!act.length && <div className="fb-plan">
        <h3>Revision plan</h3>
        <p className="hint">Tick the requests to work on. The plan is saved for Revise; nothing is posted to GitHub.</p>
        <div className="row"><button onClick={save} disabled={!picked.size || saving}>{saving ? "Saving…" : `Save plan (${picked.size})`}</button>
          {saved && <span role="status">{saved}</span>}</div>
      </div>}
    </div>
  );
}
