from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from dtf_waitwatch.database import Database
from dtf_waitwatch.models import ObservationStatus
from dtf_waitwatch.scheduler import (
    calculate_end_time,
    iter_schedule,
    mark_missed_slots,
    missed_schedule_slots,
)


def test_five_day_end_time_is_exactly_120_hours():
    start = datetime(2026, 8, 1, 12, 34, 56, tzinfo=UTC)
    end = calculate_end_time(start, 5)
    assert end - start == timedelta(hours=120)
    assert len(list(iter_schedule(start, end, 15))) == 480


def test_schedule_across_spring_dst_uses_real_utc_intervals():
    eastern = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 8, 6, 30, tzinfo=UTC)  # 01:30 EST
    slots = list(iter_schedule(start, start + timedelta(hours=1), 15))
    local_labels = [slot.astimezone(eastern).strftime("%H:%M %z") for slot in slots]
    assert local_labels == ["01:30 -0500", "01:45 -0500", "03:00 -0400", "03:15 -0400"]


def test_missed_intervals_are_inserted_once(app_config):
    database = Database(app_config.database_path)
    database.initialize()
    location_id = database.ensure_location(app_config)
    start = datetime(2026, 8, 1, 12, tzinfo=UTC)
    end = start + timedelta(hours=1)
    run_id = database.create_run(location_id, start, end, 15, "demo")
    slots = missed_schedule_slots(start, start + timedelta(minutes=46), end, 15)
    assert slots == [
        start,
        start + timedelta(minutes=15),
        start + timedelta(minutes=30),
        start + timedelta(minutes=45),
    ]
    assert (
        mark_missed_slots(
            config=app_config,
            database=database,
            run_id=run_id,
            location_id=location_id,
            slots=slots,
        )
        == 4
    )
    assert (
        mark_missed_slots(
            config=app_config,
            database=database,
            run_id=run_id,
            location_id=location_id,
            slots=slots,
        )
        == 0
    )
    assert {row["status"] for row in database.list_observations(location_id)} == {
        ObservationStatus.MISSED_DUE_TO_DOWNTIME.value
    }
