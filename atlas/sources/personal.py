"""Local data: co-op application tracker and the 30-day LeetCode/project challenge."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from atlas.config import settings


def coop_rows(path: Path | None = None) -> list[dict]:
    import openpyxl

    ws = openpyxl.load_workbook(path or settings.coop_tracker, read_only=True, data_only=True)["Tracker"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        row = {h: (v.isoformat() if isinstance(v, (date, datetime)) else v) for h, v in zip(header, r)}
        if "example.com" in str(row.get("Link", "")):  # template row
            continue
        out.append(row)
    return out


def coop_summary(path: Path | None = None, today: date | None = None) -> dict:
    rows = coop_rows(path)
    today = today or date.today()
    by_status = Counter(str(r.get("Status") or "Unknown") for r in rows)
    ready = [r for r in rows if r.get("Status") == "Ready to Apply"]
    ready.sort(key=lambda r: -(r.get("Fit Rank") or 0))

    def stale(r):
        try:
            return date.fromisoformat(str(r.get("Last Updated"))[:10]) < today - timedelta(days=14)
        except ValueError:
            return False
    return {
        "total": len(rows),
        "by_status": dict(by_status),
        "ready_to_apply_top": [{k: r.get(k) for k in ("Company", "Role", "Fit Rank", "Link")} for r in ready[:8]],
        "applied_no_update_14d": [{k: r.get(k) for k in ("Company", "Role", "Last Updated")}
                                  for r in rows if r.get("Status") == "Applied" and stale(r)],
    }


def challenge_day(on: date, path: Path | None = None) -> dict | None:
    plan = json.loads((path or settings.challenge).read_text())
    n = (on - date.fromisoformat(plan["start"])).days + 1
    if 1 <= n <= len(plan["days"]):
        return plan["days"][n - 1]
    return None
