from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from atlas.sources.calendar import parse_ics, timetable_events

TZ = ZoneInfo("America/Toronto")
TIMETABLE = Path(__file__).parent.parent / "data" / "timetable.example.json"

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:a1
SUMMARY:Assignment 1 - Due
LOCATION:CS 301A:Operating Systems
DTSTART:20261002T035900Z
DTEND:20261002T035900Z
END:VEVENT
BEGIN:VEVENT
UID:m1
SUMMARY:Club meeting
DTSTART;TZID=America/Toronto:20260929T180000
DTEND;TZID=America/Toronto:20260929T190000
RRULE:FREQ=WEEKLY;COUNT=3
END:VEVENT
END:VCALENDAR
"""


def day(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=TZ)


def test_ics_recurrence_and_deadlines():
    events = parse_ics(ICS, "Avenue", day(2026, 9, 28), day(2026, 10, 14))
    titles = [(e.title, e.kind) for e in events]
    assert titles.count(("Club meeting", "event")) == 3
    due = next(e for e in events if e.kind == "deadline")
    assert due.title == "[CS 301A] Assignment 1 - Due"
    assert due.start == day(2026, 10, 1, 23, 59)  # UTC converted to Toronto time


def test_monday_work_ends_an_hour_before_lab():
    events = timetable_events(day(2026, 9, 28), day(2026, 9, 28, 23, 59), TIMETABLE)
    work = next(e for e in events if e.kind == "work")
    assert (work.start.hour, work.end.hour, work.end.minute) == (8, 9, 30)
    assert [e.title for e in events if e.kind == "class"] == ["CS 301 Operating Systems Laboratory L04", "CS 201 Logic Lecture"]


def test_thursday_work_capped_at_ten_and_no_work_friday():
    thu = timetable_events(day(2026, 10, 1), day(2026, 10, 1, 23, 59), TIMETABLE)
    assert next(e for e in thu if e.kind == "work").end.hour == 10
    fri = timetable_events(day(2026, 10, 2), day(2026, 10, 2, 23, 59), TIMETABLE)
    assert not [e for e in fri if e.kind == "work"]


def test_sunday_work_and_no_classes_after_term():
    sun = timetable_events(day(2026, 9, 27), day(2026, 9, 27, 23, 59), TIMETABLE)
    assert [e.kind for e in sun] == ["work"]
    winter = timetable_events(day(2027, 1, 12), day(2027, 1, 12, 23, 59), TIMETABLE)
    assert not [e for e in winter if e.kind == "class"]
