"""Tool implementations shared by the specialist agents."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta

from atlas.agents.base import Tool, schema
from atlas.config import settings
from atlas.db import DB
from atlas.sources import calendar, google, personal


def now() -> datetime:
    return datetime.now(settings.tz)


def _day_range(start_date: str, end_date: str | None) -> tuple[datetime, datetime]:
    s = datetime.combine(date.fromisoformat(start_date), time.min, settings.tz)
    e = datetime.combine(date.fromisoformat(end_date or start_date), time.max, settings.tz)
    return s, e


async def get_events(start_date: str, end_date: str | None = None, kinds: list[str] | None = None) -> dict:
    s, e = _day_range(start_date, end_date)
    events, errors = await calendar.all_events(s, e)
    if kinds:
        events = [ev for ev in events if ev.kind in kinds]
    return {"events": [ev.to_dict() for ev in events], "feed_errors": errors}


async def get_deadlines(db: DB, days_ahead: int = 14) -> dict:
    s = now()
    events, errors = await calendar.all_events(s, s + timedelta(days=days_ahead))
    return {
        "calendar_deadlines": [ev.to_dict() for ev in events if ev.kind == "deadline"],
        "tasks_with_due_dates": [t for t in db.tasks() if t["due"]],
        "feed_errors": errors,
    }


def _google_required():
    if not google.available():
        raise RuntimeError("Gmail isn't connected yet. Run `python -m atlas.setup_google` on the server.")


async def search_mail(query: str, max_results: int = 15, with_body: bool = False):
    _google_required()
    return await asyncio.to_thread(google.search_mail, query, min(max_results, 30), with_body)


async def read_mail(message_id: str):
    _google_required()
    return await asyncio.to_thread(google.read_mail, message_id)


# --- Tool objects --------------------------------------------------------------------------
DATE = {"type": "string", "description": "YYYY-MM-DD"}

EVENTS = Tool(
    "get_events",
    "Classes, work shifts, calendar events and due dates between two dates (inclusive), merged from "
    "the timetable, Google Calendar and the ICS feeds (Avenue to Learn, Outlook, iCloud). "
    "kind is one of class, work, event, deadline.",
    schema({"start_date": DATE, "end_date": DATE,
            "kinds": {"type": "array", "items": {"type": "string", "enum": ["class", "work", "event", "deadline"]}}},
           ["start_date"]),
    get_events,
)

MAIL_SEARCH = Tool(
    "search_mail",
    "Search Gmail with Gmail query syntax (e.g. 'in:inbox is:unread newer_than:1d', "
    "'from:recruiter subject:interview', 'label:school newer_than:7d'). Returns sender, subject, "
    "date and snippet; set with_body for the full text (slower).",
    schema({"query": {"type": "string"}, "max_results": {"type": "integer"}, "with_body": {"type": "boolean"}},
           ["query"]),
    search_mail,
)

MAIL_READ = Tool("read_mail", "Read one email's full text by id.",
                 schema({"message_id": {"type": "string"}}, ["message_id"]), read_mail)

COOP = Tool("coop_summary",
            "Co-op job hunt status from the tracker spreadsheet: counts by status, top 'Ready to Apply' "
            "listings by fit rank, and applications with no update in 14+ days.",
            schema(), lambda: personal.coop_summary())

COOP_ROWS = Tool("coop_listings", "All rows of the co-op tracker, optionally filtered by status.",
                 schema({"status": {"type": "string"}}),
                 lambda status=None: [r for r in personal.coop_rows()
                                      if not status or str(r.get("Status", "")).lower() == status.lower()])

CHALLENGE = Tool("challenge_day",
                 "The 30-day LeetCode + project challenge plan for a date: topic, core and bonus problems, project.",
                 schema({"on": DATE}, ["on"]),
                 lambda on: personal.challenge_day(date.fromisoformat(on)) or "No challenge day on that date.")


def db_tools(db: DB) -> dict[str, Tool]:
    return {
        "deadlines": Tool("get_deadlines", "Upcoming due dates from Avenue/calendars plus your own tasks with due dates.",
                          schema({"days_ahead": {"type": "integer"}}),
                          lambda days_ahead=14: get_deadlines(db, days_ahead)),
        "list_tasks": Tool("list_tasks", "Open to-dos (and done ones if include_done).",
                           schema({"include_done": {"type": "boolean"}}),
                           lambda include_done=False: db.tasks(include_done)),
        "add_task": Tool("add_task", "Save a to-do or reminder. due is ISO 8601 local time, e.g. 2026-10-02T23:59.",
                         schema({"title": {"type": "string"}, "due": {"type": "string"}, "notes": {"type": "string"}},
                                ["title"]),
                         lambda title, due=None, notes=None: {"id": db.add_task(title, due, notes)}),
        "complete_task": Tool("complete_task", "Mark a to-do done by id.",
                              schema({"task_id": {"type": "integer"}}, ["task_id"]),
                              lambda task_id: {"ok": db.complete_task(task_id)}),
        "log_mood": Tool("log_mood", "Record how the user feels: energy 1-5, a word or two for mood, optional note.",
                         schema({"energy": {"type": "integer", "minimum": 1, "maximum": 5},
                                 "mood": {"type": "string"}, "note": {"type": "string"}}),
                         lambda energy=None, mood=None, note=None: db.log_mood(energy, mood, note) or {"ok": True}),
        "recent_moods": Tool("recent_moods", "The last week of mood/energy check-ins.", schema(),
                             lambda: db.recent_moods()),
    }
