import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentState, BusEvent } from "../api";
import {
  BUILDINGS, COLORS, H, HOME, LOOKS, W, darkness, drawBuilding, drawGround, drawLetter, drawPerson,
  drawSparkle, drawTrees, windowColor, windowsOf,
} from "./world";

interface Person { x: number; y: number; tx: number; ty: number; wait: number; frame: number; step: number }
interface Letter { x0: number; y0: number; x1: number; y1: number; start: number; dur: number; color: string }
interface Spark { x: number; y: number; start: number; color: string }
interface Transient { text: string; until: number; tone: "info" | "alert" }

const SPEED = 20; // logical px per second

function randomIn(zone: { x0: number; x1: number; y0: number; y1: number }) {
  return { x: zone.x0 + Math.random() * (zone.x1 - zone.x0), y: zone.y0 + Math.random() * (zone.y1 - zone.y0) };
}

function bubbleFor(a: AgentState, t?: Transient): { text: string; tone: string } | null {
  if (t && t.until > Date.now()) return { text: t.text, tone: t.tone };
  if (a.status === "paused") return { text: "Paused", tone: "muted" };
  if (a.status === "error") return { text: "Something broke", tone: "alert" };
  if (a.status === "thinking") return { text: "", tone: "thinking" };
  if (a.status === "working") return { text: a.doing || "Working", tone: "work" };
  return null;
}

export default function Town({ agents, events, selected, onSelect }: {
  agents: Record<string, AgentState>;
  events: BusEvent[];
  selected: string | null;
  onSelect: (name: string) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const people = useRef(new Map<string, Person>());
  const letters = useRef<Letter[]>([]);
  const sparks = useRef<Spark[]>([]);
  const overlay = useRef(new Map<string, HTMLDivElement>());
  const lastEvent = useRef<number | null>(null);
  const live = useRef({ agents, selected });
  live.current = { agents, selected };

  const [transient, setTransient] = useState<Record<string, Transient>>({});
  const [, tick] = useState(0);
  const names = useMemo(() => Object.keys(agents).filter((n) => HOME[n]), [agents]);

  // Re-render once a second so timed bubbles disappear.
  useEffect(() => {
    const id = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  // Turn new events into letters, sparkles and short-lived bubbles.
  useEffect(() => {
    if (!events.length) return;
    if (lastEvent.current === null) {  // first snapshot: don't replay history
      lastEvent.current = events[events.length - 1].id;
      return;
    }
    const fresh = events.filter((e) => e.id > (lastEvent.current ?? 0));
    if (!fresh.length) return;
    lastEvent.current = fresh[fresh.length - 1].id;
    const now = performance.now();
    const notes: Record<string, Transient> = {};
    const say = (name: string, text: string, secs = 3, tone: Transient["tone"] = "info") => {
      notes[name] = { text, until: Date.now() + secs * 1000, tone };
    };
    const title = (n?: string) => (n && agents[n]?.title) || n || "";
    const hq = HOME.atlas;

    for (const e of fresh) {
      const home = HOME[e.agent];
      if (e.type === "delegate" && e.to && HOME[e.to]) {
        const to = HOME[e.to];
        letters.current.push({ x0: hq.door.x, y0: hq.y + 20, x1: to.door.x, y1: to.door.y - 14,
          start: now, dur: 1100, color: COLORS[e.to] ?? "#fff" });
        say("atlas", `Asking ${title(e.to)}`, 3);
        say(e.to, "Got a letter!", 2);
      } else if (e.type === "reply" && e.agent !== "atlas" && home) {
        letters.current.push({ x0: home.door.x, y0: home.door.y - 14, x1: hq.door.x, y1: hq.y + 20,
          start: now, dur: 1100, color: COLORS[e.agent] ?? "#fff" });
        sparks.current.push({ x: home.door.x, y: home.door.y - 16, start: now, color: "#ffe07a" });
        if (e.text.trim() !== "NOTHING") say(e.agent, "Done, sending it back", 2.5);
      } else if (e.type === "message_in") {
        say("atlas", e.source === "web" || e.source === "telegram" ? "New request from you" : "New request", 4);
      } else if (e.type === "message_out") {
        say("atlas", e.source === "proactive" ? "Messaged you" : "Replied to you", 4);
        sparks.current.push({ x: hq.door.x, y: hq.y - 6, start: now, color: "#e0a93b" });
      } else if (e.type === "job_start") {
        say("atlas", `Ringing the bell: ${e.text}`, 5);
      } else if (e.type === "error") {
        say(e.agent, "Hit an error", 6, "alert");
      } else if (e.type === "tool_result" && e.ok === false) {
        say(e.agent, `${e.tool ?? "Tool"} failed`, 5, "alert");
      } else if (e.type === "control") {
        say(e.agent, e.text, 3);
      } else if (e.type === "blocked") {
        say(e.agent, "Paused, can't help", 3, "alert");
      }
    }
    setTransient((prev) => ({ ...prev, ...notes }));
  }, [events, agents]);

  // Animation loop.
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    let raf = 0, prev = performance.now();

    const frame = (t: number) => {
      const dt = Math.min(0.1, (t - prev) / 1000);
      prev = t;
      const { agents: states, selected: sel } = live.current;

      // move people
      for (const name of Object.keys(states)) {
        const home = HOME[name];
        if (!home) continue;
        let p = people.current.get(name);
        if (!p) {
          const s = randomIn(home.zone);
          p = { x: s.x, y: s.y, tx: s.x, ty: s.y, wait: Math.random() * 2, frame: 0, step: 0 };
          people.current.set(name, p);
        }
        const st = states[name].status;
        if (st === "thinking" || st === "working" || st === "paused") {  // report to the front door
          p.tx = home.door.x + (name === "triage" ? 10 : 0);
          p.ty = home.door.y + 6;
        } else if (Math.hypot(p.tx - p.x, p.ty - p.y) < 1) {
          p.wait -= dt;
          if (p.wait <= 0) {
            const n = randomIn(home.zone);
            p.tx = n.x; p.ty = n.y; p.wait = 1.5 + Math.random() * 4;
          }
        }
        const dx = p.tx - p.x, dy = p.ty - p.y, dist = Math.hypot(dx, dy);
        if (dist >= 1) {
          const move = Math.min(dist, SPEED * dt * (st === "idle" ? 1 : 1.8));
          p.x += (dx / dist) * move;
          p.y += (dy / dist) * move;
          p.step += dt;
          if (p.step > 0.18) { p.step = 0; p.frame++; }
        } else {
          p.frame = 0;
        }
      }

      // draw
      const dark = darkness(new Date());
      drawGround(ctx, t);
      for (const b of BUILDINGS) {
        const residents = b.agents.map((a) => states[a]).filter(Boolean);
        const active = residents.some((r) => r.status === "thinking" || r.status === "working");
        const closed = residents.length > 0 && residents.every((r) => r.paused);
        drawBuilding(ctx, b, dark > 0.15, active, closed, t);
      }
      drawTrees(ctx);
      const ordered = [...people.current.entries()].sort((a, b) => a[1].y - b[1].y);
      for (const [name, p] of ordered) {
        const s = states[name];
        if (s) drawPerson(ctx, p.x, p.y, LOOKS[name], p.frame, s.paused, name === sel);
      }
      letters.current = letters.current.filter((l) => {
        const k = (t - l.start) / l.dur;
        if (k >= 1) {
          sparks.current.push({ x: l.x1, y: l.y1, start: t, color: l.color });
          return false;
        }
        const x = l.x0 + (l.x1 - l.x0) * k;
        const y = l.y0 + (l.y1 - l.y0) * k - Math.sin(k * Math.PI) * 28;
        drawLetter(ctx, x, y, l.color);
        return true;
      });
      sparks.current = sparks.current.filter((s) => {
        const age = (t - s.start) / 600;
        if (age >= 1) return false;
        drawSparkle(ctx, s.x, s.y, age, s.color);
        return true;
      });
      if (dark > 0) {  // night: darken, then relight windows and lamps
        ctx.fillStyle = `rgba(12, 18, 48, ${dark})`;
        ctx.fillRect(0, 0, W, H);
        for (const b of BUILDINGS) {
          const active = b.agents.some((a) => ["thinking", "working"].includes(states[a]?.status));
          ctx.fillStyle = windowColor(true, active);
          for (const [wx, wy] of windowsOf(b)) ctx.fillRect(wx, wy, 5, 4);
        }
      }

      // pin DOM labels and bubbles to the sprites
      for (const [name, p] of people.current) {
        const el = overlay.current.get(name);
        if (el) {
          el.style.left = `${(p.x / W) * 100}%`;
          el.style.top = `${(p.y / H) * 100}%`;
        }
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  const pick = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    const y = ((e.clientY - r.top) / r.height) * H;
    let best: string | null = null, bestD = 9;
    for (const [name, p] of people.current) {
      const d = Math.hypot(p.x - x, p.y - 5 - y);
      if (d < bestD) { best = name; bestD = d; }
    }
    if (!best) {
      const b = BUILDINGS.find((b) => x >= b.x - 3 && x <= b.x + b.w + 3 && y >= b.y - 14 && y <= b.y + b.h);
      best = b?.agents[0] ?? null;
    }
    if (best) onSelect(best);
  };

  return (
    <div className="town">
      <canvas ref={canvas} width={W} height={H} onPointerDown={pick} aria-label="Atlas Town: live view of your agents" />
      <div className="town-overlay" aria-hidden="true">
        {BUILDINGS.map((b) => (
          <span key={b.id} className="sign" style={{ left: `${((b.x + b.w / 2) / W) * 100}%`, top: `${((b.y + (b.id === "hq" ? 20 : 2)) / H) * 100}%` }}>
            {b.name}
          </span>
        ))}
        {names.map((name) => {
          const bubble = bubbleFor(agents[name], transient[name]);
          return (
            <div key={name} className={`pin${name === selected ? " selected" : ""}`}
              ref={(el) => { if (el) overlay.current.set(name, el); else overlay.current.delete(name); }}>
              {bubble && (
                <div className={`bubble ${bubble.tone}`}>
                  {bubble.tone === "thinking" ? <span className="dots"><i /><i /><i /></span> : bubble.text}
                </div>
              )}
              <span className="name" style={{ color: COLORS[name] }}>{agents[name].title}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
