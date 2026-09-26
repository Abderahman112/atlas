from datetime import datetime, time
from zoneinfo import ZoneInfo

from atlas.scheduler import Spec, next_run

TZ = ZoneInfo("America/Toronto")


def test_daily_job_skips_to_allowed_weekday():
    spec = Spec("m", "Morning", "", at=time(9, 0), days=("fri", "sat"))
    after = datetime(2026, 9, 27, 10, 0, tzinfo=TZ)  # Sunday
    assert next_run(spec, after) == datetime(2026, 10, 2, 9, 0, tzinfo=TZ)  # Friday


def test_daily_job_later_today_and_interval():
    spec = Spec("e", "Evening", "", at=time(21, 0))
    after = datetime(2026, 9, 28, 20, 59, tzinfo=TZ)
    assert next_run(spec, after) == datetime(2026, 9, 28, 21, 0, tzinfo=TZ)
    assert next_run(Spec("r", "R", "", every=300), after).minute == 4
