"""Google Calendar + Gmail, read-only. Credentials come from secrets/token.json,
created once with `python -m atlas.setup_google`."""
from __future__ import annotations

import base64
import re
from datetime import datetime
from functools import lru_cache
from html import unescape

from atlas.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def available() -> bool:
    return settings.google_token.exists()


@lru_cache(maxsize=1)
def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(settings.google_token), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        settings.google_token.write_text(creds.to_json())
    return creds


def _svc(name: str, version: str):
    from googleapiclient.discovery import build

    creds = _creds()
    if not creds.valid:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    return build(name, version, credentials=creds, cache_discovery=False)


# --- Calendar ------------------------------------------------------------------------------
def calendar_events(start: datetime, end: datetime):
    from atlas.sources.calendar import Event, _aware

    svc = _svc("calendar", "v3")
    out = []
    for cal in svc.calendarList().list().execute().get("items", []):
        if not cal.get("selected", True):
            continue
        items = svc.events().list(calendarId=cal["id"], timeMin=start.isoformat(), timeMax=end.isoformat(),
                                  singleEvents=True, orderBy="startTime", maxResults=250).execute()
        for it in items.get("items", []):
            s, e = it["start"], it.get("end", {})
            raw_s = s.get("dateTime") or s.get("date")
            raw_e = e.get("dateTime") or e.get("date")
            parse = lambda v: datetime.fromisoformat(v) if "T" in v else datetime.fromisoformat(v).date()  # noqa: E731
            st, all_day = _aware(parse(raw_s), start.tzinfo)
            en = _aware(parse(raw_e), start.tzinfo)[0] if raw_e else None
            out.append(Event(it.get("summary", "(untitled)"), st, en, f"Google: {cal.get('summary', '')}",
                             it.get("location", ""), all_day, f"g:{it['id']}"))
    return out


# --- Gmail ---------------------------------------------------------------------------------
def _body_text(payload: dict, limit: int = 4000) -> str:
    def walk(p):
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            yield base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8", "replace")
        for part in p.get("parts", []) or []:
            yield from walk(part)
    text = "\n".join(walk(payload))
    if not text and payload.get("body", {}).get("data"):  # HTML-only mail
        html = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
        text = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:limit]


def search_mail(query: str = "in:inbox is:unread newer_than:2d", max_results: int = 15,
                with_body: bool = False) -> list[dict]:
    svc = _svc("gmail", "v1")
    ids = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute().get("messages", [])
    out = []
    for m in ids:
        fmt = "full" if with_body else "metadata"
        msg = svc.users().messages().get(userId="me", id=m["id"], format=fmt,
                                         metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        item = {"id": m["id"], "thread": msg["threadId"], "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""), "date": headers.get("Date", ""),
                "snippet": unescape(msg.get("snippet", "")), "labels": msg.get("labelIds", [])}
        if with_body:
            item["body"] = _body_text(msg["payload"])
        out.append(item)
    return out


def read_mail(message_id: str) -> dict:
    svc = _svc("gmail", "v1")
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    return {"id": message_id, "from": headers.get("From", ""), "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""), "date": headers.get("Date", ""),
            "body": _body_text(msg["payload"], 8000)}
