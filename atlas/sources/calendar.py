"""Everything with a time attached: classes, work shifts, ICS feeds (Avenue, Outlook, iCloud)
and Google Calendar, merged into one list of Event objects."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path

import httpx
import icalendar
import recurring_ical_events

from atlas.config import settings

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime | None
    source: str
    location: str = ""
    all_day: bool = False
    uid: str = ""
    kind: str = "event"  # event | class | work | deadline

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat() if self.end else None
        return d


def _aware(v, tz) -> tuple[datetime, bool]:
    """ICS values can be dates (all-day) or naive/aware datetimes; normalise to aware."""
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=tz)).astimezone(tz), False
    return datetime.combine(v, dtime.min, tz), True


# --- timetable ---------------------------------------------------------------------------
def timetable_events(start: datetime, end: datetime, path: Path | None = None) -> list[Event]:
    path = path or settings.timetable
    if not path.exists():
        path = path.with_name("timetable.example.json")
    tt = json.loads(path.read_text())
    tz = start.tzinfo
    t0, t1 = date.fromisoformat(tt["term_start"]), date.fromisoformat(tt["term_end"])
    out: list[Event] = []
    d = start.date()
    while d <= end.date():
        wd = DAYS[d.weekday()]
        at = lambda hm: datetime.combine(d, dtime.fromisoformat(hm), tz)  # noqa: E731
        classes = [c for c in tt["classes"] if c["day"] == wd] if t0 <= d <= t1 else []
        for c in classes:
            out.append(Event(f'{c["course"]} {c["kind"]}', at(c["start"]), at(c["end"]),
                             "timetable", c["where"], uid=f'class:{c["course"]}:{c["kind"]}:{d}', kind="class"))
        w = tt.get("work")
        if w and wd in w["days"]:
            w_end = at("10:00")
            if classes:
                w_end = min(w_end, min(at(c["start"]) for c in classes) - timedelta(hours=1))
            out.append(Event(w["name"], at(w["start"]), w_end, "timetable", uid=f"work:{d}", kind="work"))
        d += timedelta(days=1)
    return [e for e in out if e.end and e.end > start and e.start < end]


# --- ICS feeds ---------------------------------------------------------------------------
_ics_cache: dict[str, tuple[float, bytes]] = {}


async def _fetch(url: str, ttl: int = 600) -> bytes:
    hit = _ics_cache.get(url)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(url.replace("webcal://", "https://"))
        r.raise_for_status()
    _ics_cache[url] = (time.monotonic(), r.content)
    return r.content


def parse_ics(raw: bytes, label: str, start: datetime, end: datetime) -> list[Event]:
    tz = start.tzinfo
    cal = icalendar.Calendar.from_ical(raw)
    out = []
    for comp in recurring_ical_events.of(cal).between(start, end):
        s, all_day = _aware(comp.get("DTSTART").dt, tz)
        e = comp.get("DTEND")
        e_dt = _aware(e.dt, tz)[0] if e else None
        title = str(comp.get("SUMMARY", "(untitled)"))
        # Avenue/D2L due dates are zero-length events titled "... - Due" / "Due: ..."
        kind = "deadline" if "due" in title.lower() or e_dt is None or e_dt == s else "event"
        out.append(Event(title, s, e_dt, label, str(comp.get("LOCATION", "")), all_day,
                         f'{label}:{comp.get("UID", title)}:{s.isoformat()}', kind))
    return out


async def ics_events(start: datetime, end: datetime) -> tuple[list[Event], list[str]]:
    events, errors = [], []
    for spec in settings.ics_feeds:
        label, _, url = spec.partition("|")
        try:
            events += parse_ics(await _fetch(url), label, start, end)
        except Exception as exc:  # one broken feed must not hide the others
            errors.append(f"{label}: {exc}")
    return events, errors


# --- aggregate ---------------------------------------------------------------------------
async def all_events(start: datetime, end: datetime) -> tuple[list[Event], list[str]]:
    from atlas.sources import google  # optional dependency on Google credentials

    events = timetable_events(start, end)
    ics, errors = await ics_events(start, end)
    events += ics
    if google.available():
        try:
            events += await asyncio.to_thread(google.calendar_events, start, end)
        except Exception as exc:
            errors.append(f"Google Calendar: {exc}")
    events.sort(key=lambda e: e.start)
    return events, errors
