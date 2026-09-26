import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, connect, savedToken, saveToken, Unauthorized } from "./api";
import type { AgentState, BusEvent, Conn, JobState, ServerMsg } from "./api";
import { AgentCard, Chat, Feed, Routines, StatusPill } from "./panel";
import type { ChatMsg } from "./panel";
import Town from "./town/Town";
import { COLORS } from "./town/world";

interface State {
  agents: Record<string, AgentState>;
  jobs: Record<string, JobState>;
  events: BusEvent[];
  snapshotId: number; // events up to here are covered by chat history
}

const ORDER = ["atlas", "schedule", "inbox", "school", "coop", "planner", "triage"];

function reduce(s: State, m: ServerMsg): State {
  switch (m.type) {
    case "snapshot": {
      const snap = m as Extract<ServerMsg, { type: "snapshot"; events: BusEvent[] }>;
      const last = snap.events.length ? snap.events[snap.events.length - 1].id : 0;
      return { agents: snap.agents, jobs: snap.jobs, events: snap.events, snapshotId: last };
    }
    case "agent":
      return { ...s, agents: { ...s.agents, [m.agent]: (m as { state: AgentState }).state } };
    case "job": {
      const job = (m as { job: JobState }).job;
      return { ...s, jobs: { ...s.jobs, [job.name]: job } };
    }
    default: {
      const e = m as BusEvent;
      return { ...s, events: [...s.events.slice(-399), e] };
    }
  }
}

export default function App() {
  const [token, setToken] = useState(savedToken());
  const [conn, setConn] = useState<Conn>("connecting");
  const [state, dispatch] = useReducer(reduce, { agents: {}, jobs: {}, events: [], snapshotId: 0 });
  const [selected, setSelected] = useState<string | null>("atlas");
  const [tab, setTab] = useState<"activity" | "routines" | "chat">("activity");
  const [history, setHistory] = useState<ChatMsg[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const errTimer = useRef<number>(undefined);

  const fail = useCallback((err: unknown) => {
    if (err instanceof Unauthorized) { setConn("unauthorized"); return; }
    setError(err instanceof Error ? err.message : String(err));
    window.clearTimeout(errTimer.current);
    errTimer.current = window.setTimeout(() => setError(""), 5000);
  }, []);

  useEffect(() => {
    if (!token) { setConn("unauthorized"); return; }
    const stop = connect(token, dispatch, setConn);
    return stop;
  }, [token]);

  useEffect(() => {
    if (conn !== "open") return;
    api<{ role: "user" | "assistant"; content: string; ts: string }[]>(token, "history")
      .then((rows) => setHistory(rows.map((r) => ({ role: r.role, content: r.content, ts: r.ts }))))
      .catch(fail);
  }, [conn, token, fail]);

  if (conn === "unauthorized") return <Login initial={token} onSubmit={(t) => { saveToken(t); setToken(t); setConn("connecting"); }} failed={!!token} />;

  const { agents, jobs, events } = state;
  const liveChat: ChatMsg[] = events
    .filter((e) => e.id > state.snapshotId && (e.type === "message_in" || e.type === "message_out"))
    .map((e) => ({ role: e.type === "message_in" ? "user" : "assistant", content: e.text }));
  const chat = [...history, ...liveChat, ...(busy ? [{ role: "assistant" as const, content: "Atlas is on it…", pending: true }] : [])];

  const agent = selected ? agents[selected] : undefined;
  const allPaused = Object.values(agents).length > 0 && Object.values(agents).every((a) => a.paused);
  const totalCost = Object.values(agents).reduce((sum, a) => sum + a.cost, 0);
  const busyCount = Object.values(agents).filter((a) => a.status === "thinking" || a.status === "working").length;

  const send = async (text: string) => {
    setBusy(true);
    setTab("chat");
    try { await api(token, "chat", { text }); } catch (err) { fail(err); } finally { setBusy(false); }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Atlas Town</h1>
          <span className={`conn ${conn}`}>{conn === "open" ? "Live" : conn === "connecting" ? "Connecting…" : "Reconnecting…"}</span>
        </div>
        <div className="top-stats">
          <span><b>{busyCount}</b> busy</span>
          <span><b>${totalCost.toFixed(2)}</b> est. since start</span>
          <button className={allPaused ? "primary" : "danger"}
            onClick={() => api(token, "pause_all", { paused: !allPaused }).catch(fail)}>
            {allPaused ? "Resume everyone" : "Pause everyone"}
          </button>
          <button className="ghost" onClick={() => { saveToken(""); setToken(""); }}>Sign out</button>
        </div>
      </header>

      {error && <div className="toast" role="alert">{error}</div>}

      <main className="layout">
        <div className="stage">
          <Town agents={agents} events={events} selected={selected} onSelect={setSelected} />
          <nav className="roster" aria-label="Agents">
            {ORDER.filter((n) => agents[n]).map((n) => (
              <button key={n} className={`chip${n === selected ? " on" : ""}`} onClick={() => setSelected(n)}
                style={{ ["--agent" as string]: COLORS[n] }}>
                <i aria-hidden="true" />
                <span>{agents[n].title}</span>
                <StatusPill status={agents[n].status} />
              </button>
            ))}
          </nav>
        </div>

        <aside className="side">
          {agent && (
            <AgentCard agent={agent} events={events} agents={agents}
              onPause={(paused) => api(token, `agents/${agent.name}`, { paused }).catch(fail)}
              onEffort={(effort) => api(token, `agents/${agent.name}`, { effort }).catch(fail)} />
          )}
          <div className="tabs" role="tablist">
            {(["activity", "routines", "chat"] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
                {t === "activity" ? "Activity" : t === "routines" ? "Routines" : "Chat"}
              </button>
            ))}
          </div>
          <div className="tab-body">
            {tab === "activity" && <Feed events={events} agents={agents} only={selected} />}
            {tab === "routines" && (
              <Routines jobs={jobs}
                onToggle={(name, enabled) => api(token, `jobs/${encodeURIComponent(name)}`, { enabled }).catch(fail)}
                onRun={(name) => api(token, `jobs/${encodeURIComponent(name)}/run`, {}).catch(fail)} />
            )}
            {tab === "chat" && <Chat messages={chat} onSend={send} busy={busy} />}
          </div>
        </aside>
      </main>
    </div>
  );
}

function Login({ initial, onSubmit, failed }: { initial: string; onSubmit: (t: string) => void; failed: boolean }) {
  const [value, setValue] = useState(initial);
  return (
    <div className="login">
      <form onSubmit={(e) => { e.preventDefault(); if (value.trim()) onSubmit(value.trim()); }}>
        <h1>Atlas Town</h1>
        <p>Enter the access token. Atlas prints it in its log when it starts (in demo mode it's <code>demo</code>).</p>
        <label htmlFor="token">Access token</label>
        <input id="token" type="password" autoComplete="current-password" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
        {failed && <p className="bad">That token didn't work. Check the Atlas log and try again.</p>}
        <button className="primary" type="submit">Enter town</button>
      </form>
    </div>
  );
}
