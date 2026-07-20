from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dtf_waitwatch import __version__
from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.migrations import SCHEMA_SQL, SCHEMA_VERSION
from dtf_waitwatch.models import ObservationStatus, SourceObservation


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat()


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at_utc) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_iso(datetime.now(UTC))),
            )

    def ensure_location(self, config: AppConfig) -> int:
        now = utc_iso(datetime.now(UTC))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO locations(name, address, timezone, official_url, wait_source_url,
                                      provider, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, wait_source_url) DO UPDATE SET
                    address=excluded.address, timezone=excluded.timezone,
                    official_url=excluded.official_url, provider=excluded.provider
                """,
                (
                    config.location.name,
                    config.location.address,
                    config.location.timezone,
                    config.location.official_url,
                    config.location.wait_source_url,
                    config.location.provider,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT id FROM locations WHERE name=? AND wait_source_url=?",
                (config.location.name, config.location.wait_source_url),
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def create_run(
        self,
        location_id: int,
        started_at: datetime,
        scheduled_end_at: datetime,
        interval_minutes: int,
        source_type: str,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO collection_runs(location_id, started_at_utc, scheduled_end_at_utc,
                    interval_minutes, state, source_type, app_version)
                VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    location_id,
                    utc_iso(started_at),
                    utc_iso(scheduled_end_at),
                    interval_minutes,
                    source_type,
                    __version__,
                ),
            )
            return int(cursor.lastrowid)

    def active_run(self, location_id: int, source_type: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """SELECT * FROM collection_runs
                   WHERE location_id=? AND source_type=? AND state='running'
                   ORDER BY id DESC LIMIT 1""",
                (location_id, source_type),
            ).fetchone()

    def latest_run(self, location_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM collection_runs WHERE location_id=? ORDER BY id DESC LIMIT 1",
                (location_id,),
            ).fetchone()

    def finish_run(self, run_id: int, state: str = "completed") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE collection_runs SET state=?, actual_end_at_utc=? WHERE id=?",
                (state, utc_iso(datetime.now(UTC)), run_id),
            )

    def observation_exists(
        self, run_id: int, location_id: int, party_size: int, scheduled_at: datetime
    ) -> bool:
        with self.connect() as connection:
            return (
                connection.execute(
                    """SELECT 1 FROM observations WHERE run_id=? AND location_id=?
                       AND party_size=? AND scheduled_at_utc=?""",
                    (run_id, location_id, party_size, utc_iso(scheduled_at)),
                ).fetchone()
                is not None
            )

    def insert_observation(
        self,
        *,
        run_id: int,
        location_id: int,
        party_size: int,
        scheduled_at: datetime,
        local_timezone: Any,
        observation: SourceObservation,
    ) -> bool:
        parsed = observation.parsed
        observed = observation.observed_at_utc or datetime.now(UTC)
        raw_text = parsed.raw_wait_text[:2000]
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO observations(
                    run_id, location_id, party_size, scheduled_at_utc, observed_at_utc,
                    observed_at_local, status, wait_min_minutes, wait_max_minutes,
                    wait_midpoint_minutes, wait_is_open_ended, raw_wait_text, source_url,
                    source_provider, parser_name, response_status_code, response_duration_ms,
                    content_hash, error_message, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    location_id,
                    party_size,
                    utc_iso(scheduled_at),
                    utc_iso(observed),
                    observed.astimezone(local_timezone).isoformat(),
                    parsed.status.value,
                    parsed.wait_min_minutes,
                    parsed.wait_max_minutes,
                    parsed.wait_midpoint_minutes,
                    int(parsed.wait_is_open_ended),
                    raw_text,
                    observation.source_url,
                    observation.source_provider,
                    parsed.parser_name,
                    observation.response_status_code,
                    observation.response_duration_ms,
                    parsed.content_hash,
                    parsed.error_message,
                    utc_iso(datetime.now(UTC)),
                ),
            )
            return cursor.rowcount == 1

    def insert_synthetic_status(
        self,
        *,
        run_id: int,
        location_id: int,
        party_size: int,
        scheduled_at: datetime,
        local_timezone: Any,
        status: ObservationStatus,
        message: str,
    ) -> bool:
        from dtf_waitwatch.models import ParsedWait

        return self.insert_observation(
            run_id=run_id,
            location_id=location_id,
            party_size=party_size,
            scheduled_at=scheduled_at,
            local_timezone=local_timezone,
            observation=SourceObservation(
                parsed=ParsedWait(status=status, raw_wait_text="", error_message=message),
                source_url="",
                source_provider="synthetic-scheduler",
                observed_at_utc=datetime.now(UTC),
            ),
        )

    def list_observations(
        self, location_id: int, party_size: int | None = None
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM observations WHERE location_id=?"
        params: list[Any] = [location_id]
        if party_size is not None:
            sql += " AND party_size=?"
            params.append(party_size)
        sql += " ORDER BY scheduled_at_utc"
        with self.connect() as connection:
            return list(connection.execute(sql, params).fetchall())

    def list_actual_waits(self, location_id: int, party_size: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """SELECT * FROM actual_waits WHERE location_id=? AND party_size=?
                       ORDER BY joined_at_utc""",
                    (location_id, party_size),
                ).fetchall()
            )

    def record_actual(
        self,
        *,
        location_id: int,
        party_size: int,
        joined_at: datetime,
        seated_at: datetime,
        displayed_min: int | None = None,
        displayed_max: int | None = None,
        notes: str = "",
    ) -> int:
        minutes = (seated_at - joined_at).total_seconds() / 60
        if minutes < 0:
            raise ValueError("seated-at must not be before joined-at")
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO actual_waits(location_id, party_size, joined_at_utc,
                   seated_at_utc, actual_wait_minutes, displayed_wait_min_minutes,
                   displayed_wait_max_minutes, notes, created_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    location_id,
                    party_size,
                    utc_iso(joined_at),
                    utc_iso(seated_at),
                    minutes,
                    displayed_min,
                    displayed_max,
                    notes,
                    utc_iso(datetime.now(UTC)),
                ),
            )
            return int(cursor.lastrowid)

    def export_csv(self, output: str | Path, location_id: int) -> int:
        rows = self.list_observations(location_id)
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        columns = [description[1] for description in self._observation_columns()]
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row[column] for column in columns})
        return len(rows)

    def _observation_columns(self) -> Iterable[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute("PRAGMA table_info(observations)").fetchall())
