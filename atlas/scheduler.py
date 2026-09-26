"""A tiny asyncio scheduler for Atlas's routines: interval jobs and daily jobs on chosen weekdays."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Awaitable, Callable

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass
class Spec:
    name: str
    title: str
    when: str                      # human-readable, shown in the UI
    every: int | None = None       # seconds, for interval jobs
    at: time | None = None         # local time, for daily jobs
    days: tuple[str, ...] = ()     # empty = every day


def next_run(spec: Spec, after: datetime) -> datetime:
    if spec.every:
        return after + timedelta(seconds=spec.every)
    allowed = {WEEKDAYS[d] for d in spec.days} or set(range(7))
    candidate = datetime.combine(after.date(), spec.at, after.tzinfo)
    for _ in range(8):
        if candidate > after and candidate.weekday() in allowed:
            return candidate
        candidate += timedelta(days=1)
    raise ValueError(f"no run day for {spec.name}")


async def run_forever(specs: list[Spec], run: Callable[[str], Awaitable[None]],
                      now: Callable[[], datetime], on_plan: Callable[[str, datetime], None]) -> None:
    """Fire each job at its next time. Interval jobs first run shortly after start."""
    start = now()
    due = {s.name: (start + timedelta(seconds=15) if s.every else next_run(s, start)) for s in specs}
    for name, t in due.items():
        on_plan(name, t)
    while True:
        current = now()
        for s in specs:
            if due[s.name] <= current:
                asyncio.create_task(run(s.name))
                due[s.name] = next_run(s, current)
                on_plan(s.name, due[s.name])
        await asyncio.sleep(min(5.0, max(0.5, (min(due.values()) - now()).total_seconds())))
