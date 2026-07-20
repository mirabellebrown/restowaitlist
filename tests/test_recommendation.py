from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dtf_waitwatch.database import Database
from dtf_waitwatch.models import SourceObservation
from dtf_waitwatch.parsing import parse_wait_text
from dtf_waitwatch.recommendation import parse_target, recommend, weighted_quantile


def _add_history(database, config, local_datetimes, texts, party_size=2):
    location_id = database.ensure_location(config)
    utc_datetimes = [value.astimezone(UTC) for value in local_datetimes]
    run_id = database.create_run(
        location_id,
        min(utc_datetimes),
        max(utc_datetimes) + timedelta(minutes=15),
        15,
        "demo",
    )
    for scheduled, text in zip(utc_datetimes, texts, strict=True):
        database.insert_observation(
            run_id=run_id,
            location_id=location_id,
            party_size=party_size,
            scheduled_at=scheduled,
            local_timezone=config.timezone,
            observation=SourceObservation(
                parsed=parse_wait_text(text),
                source_url="demo://test",
                source_provider="synthetic-test",
                observed_at_utc=scheduled,
            ),
        )
    database.finish_run(run_id)
    return location_id


def test_weighted_quantiles_and_risk_percentiles():
    values = [10, 20, 100]
    assert weighted_quantile(values, [1, 8, 1], 0.5) == 20
    assert weighted_quantile(values, [1, 8, 1], 0.8) == 20
    assert weighted_quantile(values, [1, 1, 8], 0.9) == 100
    with pytest.raises(ValueError):
        weighted_quantile([], [], 0.8)


def test_recommendation_fallback_hierarchy(app_config):
    database = Database(app_config.database_path)
    database.initialize()
    start = datetime(2026, 7, 27, 17, 30, tzinfo=app_config.timezone)
    local_datetimes = [start + timedelta(days=offset) for offset in range(5)]
    location_id = _add_history(database, app_config, local_datetimes, ["60 min"] * 5)
    target = datetime(2026, 8, 8, 19, 0, tzinfo=app_config.timezone)  # Saturday
    result = recommend(
        database=database,
        config=app_config,
        location_id=location_id,
        target_local=target,
        party_size=2,
        risk=0.8,
    )
    assert result.fallback_level == "all_days_nearby_time"

    # Add three independent Saturdays, which must take precedence over all-day history.
    saturday_dates = [
        datetime(2026, 7, 11, 17, 30, tzinfo=app_config.timezone),
        datetime(2026, 7, 18, 17, 30, tzinfo=app_config.timezone),
        datetime(2026, 7, 25, 17, 30, tzinfo=app_config.timezone),
    ]
    _add_history(database, app_config, saturday_dates, ["70 min"] * 3)
    result = recommend(
        database=database,
        config=app_config,
        location_id=location_id,
        target_local=target,
        party_size=2,
        risk=0.8,
    )
    assert result.fallback_level == "same_weekday"
    assert result.independent_dates == 3


def test_adjacent_slots_count_as_one_independent_date_and_warn(app_config):
    database = Database(app_config.database_path)
    database.initialize()
    base = datetime(2026, 8, 1, 17, 0, tzinfo=app_config.timezone)
    local_datetimes = [base + timedelta(minutes=15 * index) for index in range(8)]
    location_id = _add_history(database, app_config, local_datetimes, ["45 min"] * 8)
    target = datetime(2026, 8, 8, 19, 0, tzinfo=app_config.timezone)
    result = recommend(
        database=database,
        config=app_config,
        location_id=location_id,
        target_local=target,
        party_size=2,
        risk=0.8,
    )
    assert result.independent_dates == 1
    assert result.confidence == "very low"
    assert any("Fewer than three" in warning for warning in result.warnings)


def test_actual_wait_calibration_uses_capped_median(app_config):
    database = Database(app_config.database_path)
    database.initialize()
    local_datetimes = [
        datetime(2026, 7, 10 + index, 17, 30, tzinfo=app_config.timezone) for index in range(5)
    ]
    location_id = _add_history(database, app_config, local_datetimes, ["50-70 mins"] * 5)
    for difference in (20, 30, 200):
        joined = datetime(2026, 7, 1, 17, tzinfo=app_config.timezone)
        database.record_actual(
            location_id=location_id,
            party_size=2,
            joined_at=joined,
            seated_at=joined + timedelta(minutes=60 + difference),
            displayed_min=50,
            displayed_max=70,
        )
    result = recommend(
        database=database,
        config=app_config,
        location_id=location_id,
        target_local=datetime(2026, 8, 1, 19, tzinfo=app_config.timezone),
        party_size=2,
        risk=0.8,
    )
    assert result.calibration_minutes == 30
    assert result.p50_minutes == 90


def test_recommendation_never_precedes_opening(app_config):
    app_config.opening_hours = {
        day: ["17:00-23:00"]
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    }
    database = Database(app_config.database_path)
    database.initialize()
    local_datetimes = [
        datetime(2026, 7, 10 + index, 17, 0, tzinfo=app_config.timezone) for index in range(5)
    ]
    location_id = _add_history(database, app_config, local_datetimes, ["180 min"] * 5)
    target = datetime(2026, 8, 1, 19, 0, tzinfo=app_config.timezone)
    result = recommend(
        database=database,
        config=app_config,
        location_id=location_id,
        target_local=target,
        party_size=2,
        risk=0.9,
    )
    assert result.recommended_join_local.hour >= 17
    assert any("earliest candidate" in warning for warning in result.warnings)


def test_range_rules_use_midpoint_for_p50_and_upper_for_conservative(app_config):
    database = Database(app_config.database_path)
    database.initialize()
    local_datetimes = [
        datetime(2026, 7, 10 + index, 17, 30, tzinfo=app_config.timezone) for index in range(5)
    ]
    location_id = _add_history(database, app_config, local_datetimes, ["70-90 mins"] * 5)
    result = recommend(
        database=database,
        config=app_config,
        location_id=location_id,
        target_local=datetime(2026, 8, 1, 19, tzinfo=app_config.timezone),
        party_size=2,
        risk=0.8,
    )
    assert result.p50_minutes == 80
    assert result.p80_minutes == 90


def test_target_parsing_handles_dst_offset_and_natural_date(app_config):
    explicit = parse_target("2026-11-01T01:30:00-04:00", app_config.timezone)
    assert explicit.utcoffset() == timedelta(hours=-4)
    now = datetime(2026, 7, 20, 12, tzinfo=UTC)  # Monday
    natural = parse_target("next Saturday 19:00", app_config.timezone, now=now)
    assert natural.weekday() == 5
    assert natural.hour == 19
    assert natural.date().isoformat() == "2026-07-25"
