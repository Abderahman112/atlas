from datetime import date

import openpyxl

from atlas.sources.personal import challenge_day, coop_summary


def test_coop_summary(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tracker"
    ws.append(["Company", "Role", "Link", "Status", "Last Updated", "Fit Rank"])
    ws.append(["Acme", "Template", "https://example.com/x", "Found", "2026-09-01", 1])
    ws.append(["Visier", "Test Dev", "https://v", "Ready to Apply", "2026-09-16", 22])
    ws.append(["Kinaxis", "Test Dev", "https://k", "Ready to Apply", "2026-09-16", 30])
    ws.append(["CGI", "Automation", "https://c", "Applied", "2026-09-01", 10])
    path = tmp_path / "t.xlsx"
    wb.save(path)

    s = coop_summary(path, today=date(2026, 9, 24))
    assert s["total"] == 3
    assert [r["Company"] for r in s["ready_to_apply_top"]] == ["Kinaxis", "Visier"]
    assert [r["Company"] for r in s["applied_no_update_14d"]] == ["CGI"]


def test_challenge_day():
    assert challenge_day(date(2026, 9, 25))["topic"] == "Arrays & Hashing"
    assert challenge_day(date(2026, 9, 24)) is None
