from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from atlas.db import DB
from atlas.proactive import due_reminders
from atlas.sources.calendar import Event

TZ = ZoneInfo("America/Toronto")
NOW = datetime(2026, 9, 30, 12, 15, tzinfo=TZ)


def test_class_reminder_fires_once():
    db = DB(":memory:")
    ev = Event("CS 301 Lecture", NOW + timedelta(minutes=15), NOW + timedelta(minutes=65),
               "timetable", "Science Hall 101", uid="c1", kind="class")
    assert due_reminders([ev], [], NOW, db) == ["⏰ CS 301 Lecture at 12:30 PM · Science Hall 101"]
    assert due_reminders([ev], [], NOW, db) == []


def test_only_tightest_deadline_window_after_downtime():
    db = DB(":memory:")
    ev = Event("A1 - Due", NOW + timedelta(hours=2), None, "Avenue", uid="a1", kind="deadline")
    msgs = due_reminders([ev], [], NOW, db)
    assert len(msgs) == 1 and "3 hours" in msgs[0]
    assert due_reminders([ev], [], NOW, db) == []


def test_task_due_windows_progress():
    db = DB(":memory:")
    db.add_task("Email TA", (NOW + timedelta(hours=30)).isoformat())
    assert "3 days" in due_reminders([], db.tasks(), NOW, db)[0]
    later = NOW + timedelta(hours=8)
    assert "24 hours" in due_reminders([], db.tasks(), later, db)[0]


def test_history_merges_roles_and_starts_with_user():
    db = DB(":memory:")
    db.add_message(1, "assistant", "morning brief")
    db.add_message(1, "assistant", "reminder")
    db.add_message(1, "user", "thanks")
    h = db.history(1)
    assert [m["role"] for m in h] == ["user", "assistant", "user"]
    assert h[1]["content"] == "morning brief\n\nreminder"
