from datetime import UTC, datetime, timedelta

from dtf_waitwatch.database import Database
from dtf_waitwatch.models import SourceObservation
from dtf_waitwatch.parsing import parse_wait_text


def test_schema_is_idempotent_and_duplicate_observations_are_prevented(app_config):
    database = Database(app_config.database_path)
    database.initialize()
    database.initialize()
    location_id = database.ensure_location(app_config)
    scheduled = datetime(2026, 8, 1, 20, tzinfo=UTC)
    run_id = database.create_run(location_id, scheduled, scheduled + timedelta(days=5), 15, "demo")
    observation = SourceObservation(
        parsed=parse_wait_text("70-90 mins"),
        source_url="demo://test",
        source_provider="synthetic-test",
        observed_at_utc=scheduled,
    )
    first = database.insert_observation(
        run_id=run_id,
        location_id=location_id,
        party_size=2,
        scheduled_at=scheduled,
        local_timezone=app_config.timezone,
        observation=observation,
    )
    second = database.insert_observation(
        run_id=run_id,
        location_id=location_id,
        party_size=2,
        scheduled_at=scheduled,
        local_timezone=app_config.timezone,
        observation=observation,
    )
    assert first is True
    assert second is False
    assert len(database.list_observations(location_id)) == 1


def test_csv_export_preserves_raw_columns(app_config, tmp_path):
    database = Database(app_config.database_path)
    database.initialize()
    location_id = database.ensure_location(app_config)
    scheduled = datetime(2026, 8, 1, 20, tzinfo=UTC)
    run_id = database.create_run(
        location_id, scheduled, scheduled + timedelta(minutes=15), 15, "demo"
    )
    database.insert_observation(
        run_id=run_id,
        location_id=location_id,
        party_size=2,
        scheduled_at=scheduled,
        local_timezone=app_config.timezone,
        observation=SourceObservation(
            parsed=parse_wait_text("45 min"),
            source_url="demo://test",
            source_provider="synthetic-test",
            observed_at_utc=scheduled,
        ),
    )
    output = tmp_path / "export" / "waits.csv"
    assert database.export_csv(output, location_id) == 1
    text = output.read_text(encoding="utf-8")
    assert "raw_wait_text" in text
    assert "45 min" in text
