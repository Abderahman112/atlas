"""Live activity bus and agent registry: what every agent is doing, for the Atlas Town UI."""
from __future__ import annotations

import asyncio
import itertools
import time
from collections import deque
from dataclasses import asdict, dataclass, field

# Approximate $/1M tokens for claude-opus-5 (input, output, cache read, cache write).
PRICES = (5.00, 25.00, 0.50, 6.25)


@dataclass
class AgentState:
    name: str
    title: str
    role: str
    building: str
    status: str = "idle"            # idle | thinking | working | paused | error
    doing: str = ""
    paused: bool = False
    effort: str = "low"
    calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    last_active: float = 0.0

    @property
    def cost(self) -> float:
        i, o, cr, cw = PRICES
        return (self.input_tokens * i + self.output_tokens * o
                + self.cache_read_tokens * cr + self.cache_write_tokens * cw) / 1e6

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cost"] = round(self.cost, 4)
        return d


@dataclass
class JobState:
    name: str
    title: str
    when: str
    enabled: bool = True
    running: bool = False
    last_run: float = 0.0
    next_run: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Bus:
    keep: int = 400
    agents: dict[str, AgentState] = field(default_factory=dict)
    jobs: dict[str, JobState] = field(default_factory=dict)
    recent: deque = field(default_factory=deque)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    def register(self, state: AgentState) -> AgentState:
        existing = self.agents.get(state.name)
        if existing:  # keep counters and pause state across rebuilds
            state.paused, state.effort = existing.paused, existing.effort
        self.agents[state.name] = state
        return state

    def emit(self, agent: str, type: str, text: str = "", **data) -> dict:
        event = {"id": next(self._ids), "ts": time.time(), "agent": agent, "type": type,
                 "text": text[:500], **data}
        self.recent.append(event)
        while len(self.recent) > self.keep:
            self.recent.popleft()
        self._broadcast(event)
        return event

    def set_status(self, name: str, status: str, doing: str = "") -> None:
        s = self.agents.get(name)
        if not s:
            return
        s.status = "paused" if s.paused and status == "idle" else status
        s.doing = doing[:200]
        s.last_active = time.time()
        self._broadcast({"type": "agent", "agent": name, "state": s.to_dict()})

    def job_changed(self, name: str) -> None:
        self._broadcast({"type": "job", "job": self.jobs[name].to_dict()})

    def snapshot(self) -> dict:
        return {
            "type": "snapshot",
            "agents": {n: s.to_dict() for n, s in self.agents.items()},
            "jobs": {n: j.to_dict() for n, j in self.jobs.items()},
            "events": list(self.recent)[-150:],
        }

    # --- subscribers (websockets) ------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def _broadcast(self, msg: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:  # a stalled browser tab must not block the agents
                self.subscribers.discard(q)


bus = Bus()
