"""Demo mode: the real agents, tools and UI, driven by a scripted stand-in for Claude.

No API key, Telegram or Google account needed. Timetable, challenge and co-op tools run for
real; Gmail returns sample messages. Useful for trying Atlas Town and for recording demos."""
from __future__ import annotations

import asyncio
import json
import random
import uuid
from types import SimpleNamespace as NS

from atlas.agents import tools as T
from atlas.bot import SHORTCUTS
from atlas.sources import google

SAMPLE_MAIL = [
    {"id": "d1", "thread": "d1", "from": "Recruiting <jobs@example.com>", "subject": "Interview availability: Test Developer Co-op",
     "date": "", "snippet": "Could you share times you're free next week for a 30 minute call?", "labels": ["INBOX", "UNREAD"]},
    {"id": "d2", "thread": "d2", "from": "Course TA <ta@example.edu>", "subject": "Lab 3 clarification",
     "date": "", "snippet": "Part B only needs the single-threaded version.", "labels": ["INBOX", "UNREAD"]},
    {"id": "d3", "thread": "d3", "from": "Newsletter <news@example.com>", "subject": "This week in tech",
     "date": "", "snippet": "Top stories...", "labels": ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"]},
]

ROUTES = [  # keyword -> specialists the orchestrator asks
    (("brief", "review"), ["schedule", "school", "inbox", "coop", "planner"]),
    (("mail", "inbox", "email", "repl"), ["inbox"]),
    (("due", "deadline", "exam", "assignment"), ["school"]),
    (("co-op", "coop", "job", "apply"), ["coop"]),
    (("plan", "feel", "energy", "check-in"), ["planner", "schedule"]),
    (("week",), ["schedule", "school"]),
]


def install_fake_gmail() -> None:
    google.available = lambda: True
    google.search_mail = lambda query="", max_results=15, with_body=False: SAMPLE_MAIL[:max_results]
    google.read_mail = lambda message_id: {**next(m for m in SAMPLE_MAIL if m["id"] == message_id),
                                           "body": "(demo message body)"}
    google.calendar_events = lambda start, end: []


def _summarise(result: str) -> str:
    try:
        data = json.loads(result)
    except ValueError:
        return result[:200]
    if isinstance(data, dict) and "events" in data:
        items = [f"• {e['start'][11:16]} {e['title']}" for e in data["events"][:6]]
        return "\n".join(items) or "• Nothing scheduled"
    if isinstance(data, dict) and "by_status" in data:
        return "• " + ", ".join(f"{v} {k}" for k, v in data["by_status"].items())
    if isinstance(data, dict) and "calendar_deadlines" in data:
        n = len(data["calendar_deadlines"]) + len(data["tasks_with_due_dates"])
        return f"• {n} deadline(s) in the next two weeks"
    if isinstance(data, list) and data and "subject" in data[0]:
        return "\n".join(f"• {m['from'].split('<')[0].strip()}: {m['subject']}" for m in data[:4])
    if data == []:
        return "• Nothing logged yet"
    if isinstance(data, dict) and "topic" in data:
        return f"• Challenge: {data['topic']}, {', '.join(data['core'])}"
    return result[:200]


class FakeClaude:
    def __init__(self, speed: float = 1.0):
        self.speed = speed
        self.beta = NS(messages=NS(create=self.create))

    async def create(self, *, system: str, tools: list[dict], messages: list[dict], **_) -> NS:
        await asyncio.sleep(random.uniform(0.8, 2.2) / self.speed)
        usage = NS(input_tokens=random.randint(300, 900), output_tokens=random.randint(60, 350),
                   cache_read_input_tokens=random.randint(1500, 4000), cache_creation_input_tokens=0)
        names = [t["name"] for t in tools]
        last = messages[-1]["content"]
        if isinstance(last, list) and last and isinstance(last[0], dict) and last[0].get("type") == "tool_result":
            text = "\n".join(_summarise(r["content"]) for r in last)
            if any(n.startswith("ask_") for n in names):
                text = "Here's where things stand:\n" + text + "\nAnything you want me to dig into?"
            return NS(stop_reason="end_turn", content=[NS(type="text", text=text)], usage=usage)

        request = last if isinstance(last, str) else ""
        calls = self._plan(system, names, request.lower())
        if not calls:
            return NS(stop_reason="end_turn", content=[NS(type="text", text="NOTHING" if "screen new email" in system
                                                                         else "All clear.")], usage=usage)
        return NS(stop_reason="tool_use", usage=usage,
                  content=[NS(type="tool_use", id=f"toolu_{uuid.uuid4().hex[:12]}", name=n, input=i) for n, i in calls])

    def _plan(self, system: str, names: list[str], request: str) -> list[tuple[str, dict]]:
        today = T.now().date().isoformat()
        if any(n.startswith("ask_") for n in names):
            who = next((w for keys, w in ROUTES if any(k in request for k in keys)), ["schedule", "school"])
            return [(f"ask_{w}", {"request": f"Help with: {request[-120:]}"}) for w in who]
        if "screen new email" in system:
            return []
        if "scheduling specialist" in system:
            return [("get_events", {"start_date": today})]
        if "email specialist" in system:
            return [("search_mail", {"query": "in:inbox is:unread newer_than:2d"})]
        if "academics specialist" in system:
            return [("get_deadlines", {"days_ahead": 14})]
        if "job-hunt specialist" in system:
            return [("coop_summary", {})]
        if "day-planning specialist" in system:
            return [("get_events", {"start_date": today}), ("challenge_day", {"on": today}), ("recent_moods", {})]
        return []


async def visitor(assistant) -> None:
    """Keeps the town busy: asks Atlas something, or runs a routine, every half minute or so."""
    await asyncio.sleep(4)
    prompts = list(SHORTCUTS.values())
    while True:
        if random.random() < 0.25:
            await assistant.proactive.run_job(random.choice(["morning:work", "evening", "weekly"]), manual=True)
        else:
            await assistant.chat(random.choice(prompts), source="demo")
        await asyncio.sleep(random.uniform(20, 35))
