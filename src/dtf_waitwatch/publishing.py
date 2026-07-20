"""Manual snapshot ingestion and static-table export helpers.

This module deliberately has no browser, HTTP, or provider-specific code.  A
snapshot is supplied by a person or a separately authorized data source, then
stored locally before the static GitHub Pages site is updated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.database import Database
from dtf_waitwatch.models import ObservationStatus, ParsedWait, SourceObservation
from dtf_waitwatch.parsing import parse_wait_text

SITE_SCHEMA_VERSION = 1
SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class WaitSnapshot:
    """One complete, user-supplied reading for all configured party sizes."""

    captured_at_utc: datetime
    waits: dict[int, ParsedWait]


@dataclass(frozen=True, slots=True)
class SnapshotIngestResult:
    inserted: int
    scheduled_at_utc: datetime
    skipped_reason: str | None = None


def parse_snapshot_timestamp(value: str, timezone: ZoneInfo) -> datetime:
    """Parse an ISO timestamp and normalize it to UTC.

    Naive values are intentionally interpreted in the restaurant timezone so a
    hand-entered snapshot naturally uses the restaurant's local clock.
    """

    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("captured_at must be an ISO-8601 date/time") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(UTC)


def scheduled_slot(
    captured_at_utc: datetime, timezone: ZoneInfo, interval_minutes: int
) -> datetime:
    """Floor a reading to its restaurant-local collection interval."""

    if captured_at_utc.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    if interval_minutes <= 0 or 60 % interval_minutes:
        raise ValueError("interval_minutes must be a positive divisor of 60")
    local = captured_at_utc.astimezone(timezone)
    slot = local.replace(
        minute=local.minute - (local.minute % interval_minutes), second=0, microsecond=0
    )
    return slot.astimezone(UTC)


def load_snapshot(path: str | Path, config: AppConfig) -> WaitSnapshot:
    """Load a complete JSON snapshot without accepting unrecognized wait text."""

    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Snapshot JSON is invalid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Snapshot must be a JSON object")
    if payload.get("schema_version", SNAPSHOT_SCHEMA_VERSION) != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported snapshot schema_version: {payload.get('schema_version')!r}")
    captured_value = payload.get("captured_at")
    if not isinstance(captured_value, str):
        raise ValueError("Snapshot requires a string captured_at")
    raw_waits = payload.get("waits")
    if not isinstance(raw_waits, dict):
        raise ValueError("Snapshot requires a waits object keyed by party size")

    expected = set(config.collection.party_sizes)
    parsed_waits: dict[int, ParsedWait] = {}
    actual: set[int] = set()
    for raw_party_size, raw_text in raw_waits.items():
        try:
            party_size = int(raw_party_size)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid snapshot party size: {raw_party_size!r}") from exc
        if not isinstance(raw_text, str):
            raise ValueError(f"Snapshot wait for party size {party_size} must be a string")
        parsed = parse_wait_text(raw_text)
        if parsed.status is ObservationStatus.PARSE_ERROR:
            raise ValueError(
                f"Could not parse party size {party_size} wait {raw_text!r}: {parsed.error_message}"
            )
        actual.add(party_size)
        parsed_waits[party_size] = parsed

    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing party sizes {missing}")
        if extra:
            details.append(f"unexpected party sizes {extra}")
        raise ValueError(
            "Snapshot must include exactly the configured party sizes: " + "; ".join(details)
        )

    return WaitSnapshot(
        captured_at_utc=parse_snapshot_timestamp(captured_value, config.timezone),
        waits=parsed_waits,
    )


def write_snapshot(
    path: str | Path,
    *,
    captured_at_utc: datetime,
    waits: dict[int, str],
    config: AppConfig,
) -> Path:
    """Atomically write a validated snapshot for the scheduled local sync job."""

    expected = set(config.collection.party_sizes)
    if set(waits) != expected:
        raise ValueError(f"Snapshot must include exactly party sizes {sorted(expected)}")
    for party_size, text in waits.items():
        parsed = parse_wait_text(text)
        if parsed.status is ObservationStatus.PARSE_ERROR:
            raise ValueError(
                f"Could not parse party size {party_size} wait {text!r}: {parsed.error_message}"
            )
    if captured_at_utc.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "captured_at": captured_at_utc.astimezone(config.timezone).isoformat(),
        "waits": {str(party_size): waits[party_size] for party_size in sorted(waits)},
    }
    output = Path(path)
    _write_json(output, payload)
    return output


def ingest_snapshot(
    *,
    database: Database,
    config: AppConfig,
    location_id: int,
    snapshot: WaitSnapshot,
    max_age_minutes: float | None = None,
    now: datetime | None = None,
) -> SnapshotIngestResult:
    """Persist a manual snapshot once, without pretending stale data is new."""

    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    slot = scheduled_slot(
        snapshot.captured_at_utc, config.timezone, config.collection.interval_minutes
    )
    if max_age_minutes is not None:
        if max_age_minutes <= 0:
            raise ValueError("max_age_minutes must be positive")
        age = now.astimezone(UTC) - snapshot.captured_at_utc
        if age > timedelta(minutes=max_age_minutes):
            return SnapshotIngestResult(
                inserted=0,
                scheduled_at_utc=slot,
                skipped_reason=f"snapshot is {age.total_seconds() / 60:.1f} minutes old",
            )

    pending_party_sizes = [
        party_size
        for party_size in config.collection.party_sizes
        if not database.observation_exists_in_slot(location_id, party_size, slot)
    ]
    if not pending_party_sizes:
        return SnapshotIngestResult(
            inserted=0,
            scheduled_at_utc=slot,
            skipped_reason="that table slot is already recorded",
        )

    run_id = database.create_run(
        location_id,
        slot,
        slot + timedelta(minutes=config.collection.interval_minutes),
        config.collection.interval_minutes,
        "manual-snapshot",
    )
    inserted = 0
    for party_size in pending_party_sizes:
        inserted += int(
            database.insert_observation(
                run_id=run_id,
                location_id=location_id,
                party_size=party_size,
                scheduled_at=slot,
                local_timezone=config.timezone,
                observation=SourceObservation(
                    parsed=snapshot.waits[party_size],
                    source_url=config.location.wait_source_url,
                    source_provider="manual-snapshot",
                    observed_at_utc=snapshot.captured_at_utc,
                ),
            )
        )
    database.finish_run(run_id)
    return SnapshotIngestResult(inserted=inserted, scheduled_at_utc=slot)


def build_site_payload(
    *,
    database: Database,
    config: AppConfig,
    location_id: int,
    days: int | None = 31,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a compact party-size matrix suitable for a static table page."""

    if days is not None and days <= 0:
        raise ValueError("days must be positive when provided")
    now = (now or datetime.now(UTC)).astimezone(UTC)
    cutoff = now - timedelta(days=days) if days is not None else None
    grouped: dict[str, dict[str, Any]] = {}
    latest_observation_at_utc: datetime | None = None
    for row in database.list_observations(location_id):
        scheduled_at = datetime.fromisoformat(row["scheduled_at_utc"]).astimezone(UTC)
        if cutoff is not None and scheduled_at < cutoff:
            continue
        observed_at = datetime.fromisoformat(
            row["observed_at_utc"] or row["scheduled_at_utc"]
        ).astimezone(UTC)
        if latest_observation_at_utc is None or observed_at > latest_observation_at_utc:
            latest_observation_at_utc = observed_at
        slot_key = scheduled_at.isoformat()
        slot = grouped.setdefault(
            slot_key,
            {
                "scheduled_at_utc": slot_key,
                "scheduled_at_local": scheduled_at.astimezone(config.timezone).isoformat(),
                "waits": {},
            },
        )
        party_key = str(row["party_size"])
        existing = slot["waits"].get(party_key)
        if existing is not None and existing["id"] > row["id"]:
            continue
        slot["waits"][party_key] = {
            "id": row["id"],
            "status": row["status"],
            "wait_min_minutes": row["wait_min_minutes"],
            "wait_max_minutes": row["wait_max_minutes"],
            "raw_wait_text": row["raw_wait_text"],
        }

    rows: list[dict[str, Any]] = []
    for slot in sorted(grouped.values(), key=lambda item: item["scheduled_at_utc"], reverse=True):
        waits = slot["waits"]
        for party_value in waits.values():
            party_value.pop("id", None)
        rows.append(slot)

    return {
        "schema_version": SITE_SCHEMA_VERSION,
        # This must describe data freshness, not export time. It keeps an
        # unchanged database from producing a new Pages commit every interval.
        "latest_observation_at_utc": (
            latest_observation_at_utc.isoformat() if latest_observation_at_utc else None
        ),
        "restaurant": {
            "name": config.location.name,
            "timezone": config.location.timezone,
            "official_url": config.location.official_url,
        },
        "party_sizes": config.collection.party_sizes,
        "rows": rows,
    }


def export_site_payload(
    output: str | Path,
    *,
    database: Database,
    config: AppConfig,
    location_id: int,
    days: int | None = 31,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = build_site_payload(
        database=database,
        config=config,
        location_id=location_id,
        days=days,
        now=now,
    )
    _write_json(Path(output), payload)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
