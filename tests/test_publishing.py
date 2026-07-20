from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from dtf_waitwatch.config import CollectionConfig, SourceConfig
from dtf_waitwatch.database import Database
from dtf_waitwatch.models import SourceType
from dtf_waitwatch.publishing import (
    build_site_payload,
    ingest_snapshot,
    load_snapshot,
    scheduled_slot,
    write_snapshot,
)


def _configure_for_snapshots(app_config, tmp_path):
    app_config.source = SourceConfig(
        type=SourceType.MANUAL,
        manual_snapshot_path=str(tmp_path / "inbox" / "latest-waits.json"),
    )
    app_config.collection = CollectionConfig(
        party_sizes=[2, 3, 4, 5, 6], duration_days=5, interval_minutes=15
    )
    return app_config


def test_snapshot_ingestion_exports_one_party_matrix_row(app_config, tmp_path):
    config = _configure_for_snapshots(app_config, tmp_path)
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "captured_at": "2026-08-01T16:07:00-04:00",
                "waits": {
                    "2": "No wait",
                    "3": "10-15 mins",
                    "4": "20 min",
                    "5": "30+ min",
                    "6": "Waitlist closed",
                },
            }
        ),
        encoding="utf-8",
    )
    snapshot = load_snapshot(snapshot_path, config)
    database = Database(config.database_path)
    database.initialize()
    location_id = database.ensure_location(config)

    result = ingest_snapshot(
        database=database,
        config=config,
        location_id=location_id,
        snapshot=snapshot,
        now=datetime(2026, 8, 1, 20, 8, tzinfo=UTC),
    )

    assert result.inserted == 5
    assert result.scheduled_at_utc == datetime(2026, 8, 1, 20, tzinfo=UTC)
    payload = build_site_payload(
        database=database,
        config=config,
        location_id=location_id,
        days=None,
        now=datetime(2026, 8, 2, tzinfo=UTC),
    )
    assert payload["party_sizes"] == [2, 3, 4, 5, 6]
    assert len(payload["rows"]) == 1
    waits = payload["rows"][0]["waits"]
    assert waits["2"]["status"] == "no_wait"
    assert waits["3"]["wait_min_minutes"] == 10
    assert waits["3"]["wait_max_minutes"] == 15
    assert waits["5"]["wait_max_minutes"] is None
    assert waits["6"]["status"] == "waitlist_closed"
    assert payload["latest_observation_at_utc"] == "2026-08-01T20:07:00+00:00"

    exported_again = build_site_payload(
        database=database,
        config=config,
        location_id=location_id,
        days=None,
        now=datetime(2026, 8, 3, tzinfo=UTC),
    )
    assert exported_again == payload


def test_reimporting_same_snapshot_does_not_duplicate_a_table_slot(app_config, tmp_path):
    config = _configure_for_snapshots(app_config, tmp_path)
    snapshot_path = write_snapshot(
        config.manual_snapshot_path,
        captured_at_utc=datetime(2026, 8, 1, 20, 7, tzinfo=UTC),
        waits={2: "5 min", 3: "10 min", 4: "15 min", 5: "20 min", 6: "25 min"},
        config=config,
    )
    snapshot = load_snapshot(snapshot_path, config)
    database = Database(config.database_path)
    database.initialize()
    location_id = database.ensure_location(config)

    first = ingest_snapshot(
        database=database,
        config=config,
        location_id=location_id,
        snapshot=snapshot,
    )
    second = ingest_snapshot(
        database=database,
        config=config,
        location_id=location_id,
        snapshot=snapshot,
    )

    assert first.inserted == 5
    assert second.inserted == 0
    assert second.skipped_reason == "that table slot is already recorded"
    assert len(database.list_observations(location_id)) == 5


def test_snapshot_requires_every_configured_party_size(app_config, tmp_path):
    config = _configure_for_snapshots(app_config, tmp_path)
    snapshot_path = tmp_path / "incomplete.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "captured_at": "2026-08-01T16:00:00-04:00",
                "waits": {"2": "10 min", "3": "15 min"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing party sizes"):
        load_snapshot(snapshot_path, config)


def test_snapshot_slot_uses_restaurant_local_quarter_hour(app_config, tmp_path):
    config = _configure_for_snapshots(app_config, tmp_path)
    captured = datetime(2026, 11, 1, 6, 7, tzinfo=UTC)  # 01:07 EST after the fallback.
    assert scheduled_slot(captured, config.timezone, 15) == datetime(2026, 11, 1, 6, tzinfo=UTC)
