import { useEffect, useRef, useState } from "react";
import type { AgentState, BusEvent, JobState } from "./api";
import { COLORS } from "./town/world";

export const EFFORTS = ["low", "medium", "high", "xhigh"];

const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export function relative(ts: number | null): string {
  if (!ts) return "not scheduled";
  const mins = Math.round((ts * 1000 - Date.now()) / 60000);
  if (Math.abs(mins) < 1) return "now";
  const abs = Math.abs(mins);
  const span = abs < 60 ? `${abs} min` : abs < 48 * 60 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} d`;
  return mins > 0 ? `in ${span}` : `${span} ago`;
}

const STATUS_LABEL: Record<string, string> = {
  idle: "Idle", thinking: "Thinking", working: "Working", paused: "Paused", error: "Error",
};

export function StatusPill({ status }: { status: string }) {
  return <span className={`pill ${status}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export function describe(e: BusEvent, agents: Record<string, AgentState>): string {
  const t = (n?: string) => (n && agents[n]?.title) || n || "";
  switch (e.type) {
    case "delegate": return `asked ${t(e.to)}: ${e.text}`;
    case "tool_call": return `used ${e.text}`;
    case "tool_result": return e.ok === false ? `${e.tool} failed: ${e.text}` : `${e.tool} returned results`;
    case "reply": return `answered: ${e.text}`;
    case "message_in": return `got your message: ${e.text}`;
    case "message_out": return `${e.source === "proactive" ? "messaged you" : "replied"}: ${e.text}`;
    case "job_start": return `started routine: ${e.text}`;
    case "job_end": return `finished routine: ${e.text}`;
    case "blocked": return "is paused and turned a request away";
    default: return e.text;
  }
}

// --- selected agent ---------------------------------------------------------------------------
export function AgentCard({ agent, events, agents, onPause, onEffort }: {
  agent: AgentState;
  events: BusEvent[];
  agents: Record<string, AgentState>;
  onPause: (paused: boolean) => void;
  onEffort: (effort: string) => void;
}) {
  const mine = events.filter((e) => e.agent === agent.name || e.to === agent.name).slice(-6).reverse();
  const tokens = agent.input_tokens + agent.output_tokens + agent.cache_read_tokens + agent.cache_write_tokens;
  return (
    <section className="card agent-card" style={{ ["--agent" as string]: COLORS[agent.name] }}>
      <header>
        <div>
          <h2>{agent.title}</h2>
          <p className="role">{agent.role} · lives at the {agent.building}</p>
        </div>
        <StatusPill status={agent.status} />
      </header>
      <p className="doing">{agent.doing || (agent.paused ? "Paused. Requests to this agent are turned away." : "Waiting for work.")}</p>
      <dl className="stats">
        <div><dt>Model calls</dt><dd>{agent.calls}</dd></div>
        <div><dt>Tool uses</dt><dd>{agent.tool_calls}</dd></div>
        <div><dt>Tokens</dt><dd>{tokens.toLocaleString()}</dd></div>
        <div><dt>Est. cost</dt><dd>${agent.cost.toFixed(3)}</dd></div>
      </dl>
      <div className="controls">
        <button className={agent.paused ? "primary" : ""} onClick={() => onPause(!agent.paused)}>
          {agent.paused ? "Resume" : "Pause"}
        </button>
        <div className="segmented" role="group" aria-label="Effort">
          {EFFORTS.map((e) => (
            <button key={e} aria-pressed={agent.effort === e} onClick={() => onEffort(e)}>{e}</button>
          ))}
        </div>
      </div>
      <p className="hint">Effort sets how hard this agent thinks. Higher is smarter but slower and pricier.</p>
      {mine.length > 0 && (
        <ul className="mini-feed">
          {mine.map((e) => (
            <li key={e.id}><time>{clock(e.ts)}</time>{describe(e, agents)}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- activity feed -----------------------------------------------------------------------------
export function Feed({ events, agents, only }: { events: BusEvent[]; agents: Record<string, AgentState>; only: string | null }) {
  const [filter, setFilter] = useState(false);
  const list = (filter && only ? events.filter((e) => e.agent === only || e.to === only) : events).slice(-120).reverse();
  return (
    <div className="feed">
      {only && (
        <label className="check">
          <input id="feed-filter" type="checkbox" checked={filter} onChange={(e) => setFilter(e.target.checked)} />
          Only {agents[only]?.title}
        </label>
      )}
      {list.length === 0 && <p className="empty">Nothing yet. Activity shows up here as it happens.</p>}
      <ol>
        {list.map((e) => (
          <li key={e.id} className={`ev ${e.type}${e.ok === false || e.type === "error" ? " bad" : ""}`}>
            <time>{clock(e.ts)}</time>
            <span className="who" style={{ color: COLORS[e.agent] }}>{agents[e.agent]?.title ?? e.agent}</span>
            <span className="what">{describe(e, agents)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

// --- routines ----------------------------------------------------------------------------------
export function Routines({ jobs, onToggle, onRun }: {
  jobs: Record<string, JobState>;
  onToggle: (name: string, enabled: boolean) => void;
  onRun: (name: string) => void;
}) {
  return (
    <ul className="routines">
      {Object.values(jobs).map((j) => (
        <li key={j.name} className={j.enabled ? "" : "off"}>
          <div className="r-main">
            <strong>{j.title}</strong>
            <span>{j.when} · next {j.enabled ? relative(j.next_run) : "off"}{j.last_run ? ` · last ${relative(j.last_run)}` : ""}</span>
          </div>
          <label className="switch" title={j.enabled ? "Turn off" : "Turn on"}>
            <input id={`job-${j.name}`} type="checkbox" checked={j.enabled} onChange={(e) => onToggle(j.name, e.target.checked)} />
            <span aria-hidden="true" />
            <em className="sr">{j.title} enabled</em>
          </label>
          <button onClick={() => onRun(j.name)} disabled={j.running}>{j.running ? "Running…" : "Run now"}</button>
        </li>
      ))}
    </ul>
  );
}

// --- chat --------------------------------------------------------------------------------------
type SpeechCtor = new () => {
  lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null; onerror: (() => void) | null;
  start: () => void; stop: () => void;
};

export interface ChatMsg { role: "user" | "assistant"; content: string; ts?: string; pending?: boolean }

export function Chat({ messages, onSend, busy }: { messages: ChatMsg[]; onSend: (text: string) => void; busy: boolean }) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const rec = useRef<InstanceType<SpeechCtor> | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const spoken = useRef(messages.length);
  const Speech = (window as unknown as { SpeechRecognition?: SpeechCtor; webkitSpeechRecognition?: SpeechCtor })
    .SpeechRecognition ?? (window as unknown as { webkitSpeechRecognition?: SpeechCtor }).webkitSpeechRecognition;

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [messages]);

  // Read new replies aloud when the speaker is on.
  useEffect(() => {
    const fresh = messages.slice(spoken.current).filter((m) => m.role === "assistant" && !m.pending);
    spoken.current = messages.length;
    if (speak && fresh.length && "speechSynthesis" in window) {
      const u = new SpeechSynthesisUtterance(fresh[fresh.length - 1].content.replace(/•/g, ""));
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    }
  }, [messages, speak]);

  const send = () => {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  };

  const listen = () => {
    if (!Speech) return;
    if (listening) { rec.current?.stop(); return; }
    const r = new Speech();
    r.lang = "en-CA";
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => setText(Array.from(e.results).map((res) => res[0].transcript).join(""));
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };

  return (
    <div className="chat">
      <div className="msgs">
        {messages.length === 0 && <p className="empty">Ask Atlas anything: "what do I have today?"</p>}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}${m.pending ? " pending" : ""}`}>{m.content}</div>
        ))}
        <div ref={end} />
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <textarea id="chat-input" rows={2} value={text} placeholder={listening ? "Listening…" : "Message Atlas"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <div className="composer-actions">
          {Speech && (
            <button type="button" className={listening ? "live" : ""} onClick={listen} aria-pressed={listening}>
              {listening ? "Stop" : "Talk"}
            </button>
          )}
          <button type="button" aria-pressed={speak} onClick={() => setSpeak(!speak)} title="Read replies aloud">
            {speak ? "Voice on" : "Voice off"}
          </button>
          <button type="submit" className="primary" disabled={busy || !text.trim()}>{busy ? "Waiting…" : "Send"}</button>
        </div>
      </form>
    </div>
  );
}
