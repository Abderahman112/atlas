// Talks to the Atlas control API (atlas/web.py): REST for actions, one WebSocket for live activity.

export type Status = "idle" | "thinking" | "working" | "paused" | "error";

export interface AgentState {
  name: string;
  title: string;
  role: string;
  building: string;
  status: Status;
  doing: string;
  paused: boolean;
  effort: string;
  calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  last_active: number;
  cost: number;
}

export interface JobState {
  name: string;
  title: string;
  when: string;
  enabled: boolean;
  running: boolean;
  last_run: number;
  next_run: number | null;
}

export interface BusEvent {
  id: number;
  ts: number;
  agent: string;
  type: string; // delegate | tool_call | tool_result | reply | error | message_in | message_out | job_start | job_end | control | blocked
  text: string;
  to?: string;
  tool?: string;
  ok?: boolean;
  job?: string;
  source?: string;
}

export type ServerMsg =
  | { type: "snapshot"; agents: Record<string, AgentState>; jobs: Record<string, JobState>; events: BusEvent[] }
  | { type: "agent"; agent: string; state: AgentState }
  | { type: "job"; job: JobState }
  | BusEvent;

export class Unauthorized extends Error {}

const KEY = "atlasToken";

export function savedToken(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveToken(token: string): void {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode: the token just won't be remembered */
  }
}

export async function api<T = unknown>(token: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) throw new Unauthorized("Wrong access token");
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? `Request failed (${res.status})`);
  return res.json() as Promise<T>;
}

export type Conn = "connecting" | "open" | "closed" | "unauthorized";

/** Live connection with automatic reconnect. Returns a function that closes it for good. */
export function connect(token: string, onMsg: (m: ServerMsg) => void, onConn: (c: Conn) => void): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let delay = 1000;
  let timer: number | undefined;

  const open = () => {
    onConn("connecting");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${location.host}/api/ws`);
    socket.onopen = () => socket?.send(JSON.stringify({ token }));
    socket.onmessage = (e) => {
      const msg = JSON.parse(e.data) as ServerMsg;
      if (msg.type === "snapshot") {
        delay = 1000;
        onConn("open");
      }
      onMsg(msg);
    };
    socket.onclose = (e) => {
      if (stopped) return;
      if (e.code === 4401) {
        onConn("unauthorized");
        return;
      }
      onConn("closed");
      timer = window.setTimeout(open, delay);
      delay = Math.min(delay * 2, 15000);
    };
  };
  open();
  return () => {
    stopped = true;
    window.clearTimeout(timer);
    socket?.close();
  };
}
