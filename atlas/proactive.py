"""Things Atlas does without being asked: reminders, morning brief, inbox watch, check-ins."""
from __future__ import annotations

import asyncio
import json
import logging
import time as time_mod
from datetime import datetime, time, timedelta

from atlas import scheduler
from atlas.agents import tools as T
from atlas.agents.base import Agent
from atlas.agents.team import ABOUT_USER, TOWN, UNTRUSTED
from atlas.config import settings
from atlas.db import DB
from atlas.events import JobState, bus
from atlas.scheduler import Spec
from atlas.sources import calendar, google
from atlas.sources.calendar import Event

log = logging.getLogger(__name__)

LEAD = {"class": 20, "work": 30, "event": 30}          # minutes before start
DEADLINE_WINDOWS = [(3, "3 hours"), (24, "24 hours"), (72, "3 days")]  # tightest first


def in_quiet_hours(now: datetime) -> bool:
    s, e = settings.quiet_start, settings.quiet_end
    return now.hour >= s or now.hour < e if s > e else s <= now.hour < e


def _fmt(t: datetime) -> str:
    return t.strftime("%-I:%M %p")


def due_reminders(events: list[Event], tasks: list[dict], now: datetime, db: DB) -> list[str]:
    """Reminder texts that are due now. Each (item, window) fires once; when several windows are
    already crossed (e.g. the bot was offline), only the tightest one is sent."""
    out = []
    for ev in events:
        if ev.all_day:
            continue
        if ev.kind in LEAD:
            mins = (ev.start - now).total_seconds() / 60
            if 0 <= mins <= LEAD[ev.kind] and db.claim(f"start:{ev.uid}"):
                where = f" · {ev.location}" if ev.location else ""
                out.append(f"⏰ {ev.title} at {_fmt(ev.start)}{where}")

    deadlines = [(e.title, e.start, e.uid) for e in events if e.kind == "deadline"]
    for t in tasks:
        if t["due"]:
            due = datetime.fromisoformat(t["due"])
            due = due if due.tzinfo else due.replace(tzinfo=now.tzinfo)
            deadlines.append((t["title"], due, f"task:{t['id']}"))
    for title, due, uid in deadlines:
        hours = (due - now).total_seconds() / 3600
        if hours < 0:
            continue
        crossed = [(h, label) for h, label in DEADLINE_WINDOWS if hours <= h]
        if not crossed:
            continue
        fresh = [db.claim(f"due:{uid}:{h}") for h, _ in crossed]  # claim all, send the tightest
        if fresh[0]:
            when = due.strftime("%a %-I:%M %p")
            out.append(f"📌 Due in under {crossed[0][1]}: {title} ({when})")
    return out


class Proactive:
    def __init__(self, db: DB, atlas: Agent, send):
        self.db, self.atlas, self.send = db, atlas, send
        self.triage = Agent(
            "triage",
            "You screen new email for a busy student. Given new unread messages, decide which need "
            "attention today: a reply is expected, an interview or recruiter, a professor/TA/co-op "
            "office message, or a deadline. For those, write one short line each: who, what they want, "
            "by when. If nothing needs attention, reply with exactly NOTHING.\n\n"
            f"{ABOUT_USER}\n\n{UNTRUSTED}",
            [T.MAIL_READ], settings.specialist_effort, atlas.client,
            title=TOWN["triage"][0], role=TOWN["triage"][1], building=TOWN["triage"][2],
            model=settings.triage_model)

    async def _brief(self, instruction: str) -> None:
        n = T.now()
        text = await self.atlas.ask(f"Now: {n:%A %Y-%m-%d %H:%M}.\n\n{instruction}")
        await self.send(text)

    # --- jobs (python-telegram-bot JobQueue callbacks) ------------------------------------------
    async def reminders(self) -> None:
        now = T.now()
        if in_quiet_hours(now):  # nothing is claimed overnight, so the tightest reminder fires at wake-up
            return
        events, _ = await calendar.all_events(now - timedelta(hours=1), now + timedelta(days=4))
        for msg in due_reminders(events, self.db.tasks(), now, self.db):
            await self.send(msg)

    async def morning(self) -> None:
        await self._brief(
            "Send the morning brief. Ask specialists in parallel as needed. Include: today's schedule "
            "(classes, work, events) in order; anything due in the next 72 hours; emails that need a "
            "reply; today's challenge problems and project block; one co-op next step. Keep it under "
            "15 lines and end with one encouraging line.")

    async def evening(self) -> None:
        await self._brief(
            "Evening check-in. In at most 6 lines: preview tomorrow's first commitment and anything "
            "due within 48 hours, then ask how today went and their energy from 1 to 5 so you can "
            "shape tomorrow's plan.")

    async def weekly(self) -> None:
        await self._brief(
            "Sunday weekly review. Summarise: deadlines and exams this week, busiest days, co-op "
            "pipeline (applied, ready to apply, follow-ups due), and suggest which 2-3 challenge "
            "projects fit this week. Ask if anything should move.")

    async def inbox_watch(self) -> None:
        now = T.now()
        if in_quiet_hours(now) or not google.available():
            return
        msgs = await asyncio.to_thread(google.search_mail, "in:inbox is:unread newer_than:1d", 25)
        new = [m for m in msgs if self.db.claim(f"mail:{m['id']}")]
        if not new:
            return
        listing = json.dumps([{k: m[k] for k in ("id", "from", "subject", "snippet")} for m in new],
                             ensure_ascii=False)
        verdict = await self.triage.ask(f"New unread messages:\n{listing}")
        if verdict.strip() != "NOTHING":
            await self.send("📬 " + verdict)

    # --- job control (used by the scheduler and the Atlas Town UI) ----------------------------
    def register_jobs(self) -> None:
        for spec in SPECS:
            bus.jobs[spec.name] = JobState(spec.name, spec.title, spec.when)

    async def run_job(self, name: str, manual: bool = False) -> None:
        job = bus.jobs[name]
        if job.running or (not job.enabled and not manual):
            return
        loud = manual or name not in QUIET_JOBS  # frequent background checks stay out of the feed
        job.running = True
        bus.job_changed(name)
        if loud:
            bus.emit("atlas", "job_start", job.title, job=name, manual=manual)
        try:
            await getattr(self, name.split(":")[0])()
        except Exception as exc:
            log.exception("job %s failed", name)
            bus.emit("atlas", "error", f"{job.title} failed: {exc}", job=name)
        finally:
            job.running, job.last_run = False, time_mod.time()
            bus.job_changed(name)
            if loud:
                bus.emit("atlas", "job_end", job.title, job=name)

    def planned(self, name: str, at: datetime) -> None:
        bus.jobs[name].next_run = at.timestamp()
        bus.job_changed(name)

    async def run_scheduler(self) -> None:
        self.register_jobs()
        await scheduler.run_forever(SPECS, self.run_job, T.now, self.planned)


QUIET_JOBS = {"reminders", "inbox_watch"}

# name "method:variant" -> runs Proactive.method
SPECS = [
    Spec("reminders", "Class & deadline reminders", "every 5 min", every=300),
    Spec("inbox_watch", "Inbox watch", f"every {settings.inbox_check_minutes} min",
         every=settings.inbox_check_minutes * 60),
    Spec("morning:work", "Morning brief", "7:15 AM Sun-Thu", at=time(7, 15),
         days=("sun", "mon", "tue", "wed", "thu")),
    Spec("morning:off", "Morning brief (days off)", "9:00 AM Fri-Sat", at=time(9, 0), days=("fri", "sat")),
    Spec("evening", "Evening check-in", "9:00 PM daily", at=time(21, 0)),
    Spec("weekly", "Weekly review", "Sunday 11:30 AM", at=time(11, 30), days=("sun",)),
]
