from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.database import Database
from dtf_waitwatch.models import ObservationStatus, SourceObservation
from dtf_waitwatch.sources.base import WaitSource

LOGGER = logging.getLogger("dtf_waitwatch.scheduler")


def calculate_end_time(start: datetime, days: float) -> datetime:
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")
    if days <= 0:
        raise ValueError("days must be positive")
    return start + timedelta(days=days)


def iter_schedule(start: datetime, end: datetime, interval_minutes: int) -> Iterator[datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("schedule datetimes must be timezone-aware")
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    current = start
    interval = timedelta(minutes=interval_minutes)
    while current < end:
        yield current
        current += interval


def missed_schedule_slots(
    start: datetime, now: datetime, end: datetime, interval_minutes: int
) -> list[datetime]:
    cutoff = min(now, end)
    return [slot for slot in iter_schedule(start, end, interval_minutes) if slot < cutoff]


def collect_slot(
    *,
    config: AppConfig,
    database: Database,
    source: WaitSource,
    run_id: int,
    location_id: int,
    scheduled_at: datetime,
) -> dict[int, SourceObservation] | None:
    local_scheduled = scheduled_at.astimezone(config.timezone)
    if config.opening_hours and not config.is_open(local_scheduled):
        for party_size in config.collection.party_sizes:
            inserted = database.insert_synthetic_status(
                run_id=run_id,
                location_id=location_id,
                party_size=party_size,
                scheduled_at=scheduled_at,
                local_timezone=config.timezone,
                status=ObservationStatus.RESTAURANT_CLOSED,
                message="Synthetic status: outside configured restaurant opening hours.",
            )
            if inserted:
                _log_observation(run_id, scheduled_at, party_size, "restaurant_closed")
        return None

    results = source.collect(config.collection.party_sizes, scheduled_at)
    for party_size, observation in results.items():
        inserted = database.insert_observation(
            run_id=run_id,
            location_id=location_id,
            party_size=party_size,
            scheduled_at=scheduled_at,
            local_timezone=config.timezone,
            observation=observation,
        )
        if inserted:
            _log_observation(run_id, scheduled_at, party_size, observation.parsed.status.value)
    return results


def mark_missed_slots(
    *,
    config: AppConfig,
    database: Database,
    run_id: int,
    location_id: int,
    slots: list[datetime],
) -> int:
    inserted_count = 0
    for slot in slots:
        for party_size in config.collection.party_sizes:
            inserted = database.insert_synthetic_status(
                run_id=run_id,
                location_id=location_id,
                party_size=party_size,
                scheduled_at=slot,
                local_timezone=config.timezone,
                status=ObservationStatus.MISSED_DUE_TO_DOWNTIME,
                message="The scheduled interval elapsed while the collector was not running.",
            )
            inserted_count += int(inserted)
    return inserted_count


def run_collection(
    *,
    config: AppConfig,
    database: Database,
    source: WaitSource,
    days: float | None = None,
    interval_minutes: int | None = None,
    accelerated: bool = False,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    create_report: Callable[[], None] | None = None,
) -> int:
    now_fn = now_fn or (lambda: datetime.now(UTC))
    duration = days if days is not None else config.collection.duration_days
    interval = interval_minutes or config.collection.interval_minutes
    location_id = database.ensure_location(config)
    active = database.active_run(location_id, config.source.type.value)
    if active is not None:
        run_id = int(active["id"])
        start = datetime.fromisoformat(active["started_at_utc"])
        end = datetime.fromisoformat(active["scheduled_end_at_utc"])
        interval = int(active["interval_minutes"])
        resumed = True
    else:
        now = now_fn()
        start = now - timedelta(days=duration) if accelerated else now
        end = calculate_end_time(start, duration)
        run_id = database.create_run(location_id, start, end, interval, config.source.type.value)
        resumed = False

    if accelerated:
        if config.source.type.value != "demo":
            raise ValueError("Accelerated mode is restricted to the synthetic demo source")
        for slot in iter_schedule(start, end, interval):
            collect_slot(
                config=config,
                database=database,
                source=source,
                run_id=run_id,
                location_id=location_id,
                scheduled_at=slot,
            )
        database.finish_run(run_id)
        if create_report:
            create_report()
        return run_id

    now = now_fn()
    if resumed:
        missed = mark_missed_slots(
            config=config,
            database=database,
            run_id=run_id,
            location_id=location_id,
            slots=missed_schedule_slots(start, now, end, interval),
        )
        if missed:
            LOGGER.info("Recorded %s missed observations on resume", missed)

    stop_event = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        LOGGER.info("Received signal %s; stopping cleanly", signum)
        stop_event.set()

    handlers: dict[signal.Signals, object] = {}
    if threading.current_thread() is threading.main_thread():
        for name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, name, None)
            if sig is not None:
                handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, request_stop)
    try:
        for slot in iter_schedule(start, end, interval):
            if all(
                database.observation_exists(run_id, location_id, size, slot)
                for size in config.collection.party_sizes
            ):
                continue
            now = now_fn()
            if slot < now - timedelta(seconds=1):
                mark_missed_slots(
                    config=config,
                    database=database,
                    run_id=run_id,
                    location_id=location_id,
                    slots=[slot],
                )
                continue
            seconds = max(0.0, (slot - now).total_seconds())
            while seconds > 0 and not stop_event.is_set():
                sleep_fn(min(seconds, 30.0))
                seconds = max(0.0, (slot - now_fn()).total_seconds())
            if stop_event.is_set():
                return run_id
            collect_slot(
                config=config,
                database=database,
                source=source,
                run_id=run_id,
                location_id=location_id,
                scheduled_at=slot,
            )
        database.finish_run(run_id)
        if create_report:
            create_report()
        return run_id
    finally:
        for sig, previous in handlers.items():
            signal.signal(sig, previous)


def _log_observation(run_id: int, scheduled_at: datetime, party_size: int, status: str) -> None:
    LOGGER.info(
        "Recorded scheduled observation",
        extra={
            "run_id": run_id,
            "scheduled_at_utc": scheduled_at.astimezone(UTC).isoformat(),
            "party_size": party_size,
            "status": status,
        },
    )
