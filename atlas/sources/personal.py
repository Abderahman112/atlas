"""Local data: co-op application tracker and the 30-day LeetCode/project challenge."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from atlas.config import settings


SF_DATALESS = 0x40000000  # macOS: file content offloaded to iCloud


def ensure_local(path: Path, timeout: float = 60) -> None:
    """iCloud can offload Desktop/Documents files on macOS; reading one then blocks until it downloads.
    Ask iCloud for the file up front and wait, so a read never hangs. No-op elsewhere."""
    if sys.platform != "darwin" or not shutil.which("brctl"):
        return
    offloaded = lambda: bool(getattr(os.stat(path), "st_flags", 0) & SF_DATALESS)  # noqa: E731
    if not offloaded():
        return
    subprocess.run(["brctl", "download", str(path)], capture_output=True, timeout=30)
    deadline = time.monotonic() + timeout
    while offloaded():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{path.name} is still downloading from iCloud; try again in a minute")
        time.sleep(1)


def coop_rows(path: Path | None = None) -> list[dict]:
    import openpyxl

    path = Path(path or settings.coop_tracker)
    ensure_local(path)
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)["Tracker"]
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
