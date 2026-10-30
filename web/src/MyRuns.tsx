import { useEffect, useState } from "react";
import { Loading } from "./components";
import { Link } from "react-router-dom";
import { api, ApiError } from "./api";
import ProgressView from "./Progress";

type Item = { run_id: string; title: string; repo: string; number: number; status: string; outcome: string | null;
  readiness: string | null; created_at: string; pr_url: string | null };

export function useMyRuns() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const load = () => api<Item[]>("/api/me/runs").then(setItems).catch(setErr);
  useEffect(() => { load(); }, []);
  return { items, err, load };
}

const stateText = (i: Item) =>
  i.status === "awaiting_approval" ? "Needs your approval" : i.readiness ?? (i.status === "queued" ? "Waiting to start" : "Running");

export function RunList({ items, onForget }: { items: Item[]; onForget?: (id: string) => void }) {
  return (
    <ul className="runlist">
      {items.map((i) => (
        <li key={i.run_id}>
          <Link to={`/runs/${i.run_id}`}><strong>{i.title}</strong></Link>
          <span className="hint">{i.repo} #{i.number}, {new Date(i.created_at).toLocaleString()}</span>
          <span className={`pill pill-${i.status}`}>{stateText(i)}</span>
          {i.pr_url && <a href={i.pr_url}>Pull request</a>}
          {onForget && <button className="linklike" onClick={() => onForget(i.run_id)}>Forget this run</button>}
        </li>
      ))}
    </ul>
  );
}

export default function MyRuns() {
  const { items, err, load } = useMyRuns();
  const forget = (id: string) => api(`/api/runs/${id}/access`, { method: "DELETE" }).catch(() => null).then(load);
  if (err) return <section className="panel failed"><h1>Couldn't load your runs</h1><p>{err.message}</p><button onClick={load}>Try again</button></section>;
  if (!items) return <Loading label="Loading your runs…" />;
  return (
    <section>
      <h1>My runs</h1>
      <p className="hint">These runs open only in this browser. Sign in with GitHub to see them on other devices.</p>
      {!!items.length && <ProgressView />}
      {items.length ? <RunList items={items} onForget={forget} />
        : <div className="panel empty"><h2>No runs yet. Paste an issue to start.</h2>
            <p>Each run you start in this browser shows up here, with its proof and report.</p><Link className="button" to="/">New run</Link></div>}
    </section>
  );
}
