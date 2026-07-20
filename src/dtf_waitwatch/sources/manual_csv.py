from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.models import ObservationStatus, ParsedWait, SourceObservation
from dtf_waitwatch.parsing import content_hash, parse_wait_text

REQUIRED_COLUMNS = {"observed_at_local", "party_size", "status", "raw_wait_text"}


def read_manual_csv(path: str | Path, timezone: ZoneInfo) -> list[dict[str, object]]:
    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Manual CSV is missing columns: {', '.join(sorted(missing))}")
        rows: list[dict[str, object]] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                observed = datetime.fromisoformat(row["observed_at_local"].strip())
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone)
                status = ObservationStatus(row["status"].strip())
                raw = row.get("raw_wait_text", "").strip()
                parsed = parse_wait_text(raw)
                wait_min = _optional_int(row.get("wait_min_minutes"))
                wait_max = _optional_int(row.get("wait_max_minutes"))
                midpoint = (
                    (wait_min + wait_max) / 2
                    if wait_min is not None and wait_max is not None
                    else float(wait_min)
                    if wait_min is not None
                    else None
                )
                rows.append(
                    {
                        "observed_at": observed,
                        "party_size": int(row["party_size"]),
                        "parsed": ParsedWait(
                            status=status,
                            wait_min_minutes=wait_min,
                            wait_max_minutes=wait_max,
                            wait_midpoint_minutes=midpoint,
                            wait_is_open_ended=wait_min is not None and wait_max is None,
                            raw_wait_text=raw[:2000],
                            content_hash=content_hash(raw[:2000]),
                            parser_name="manual-csv-v1",
                            error_message=(
                                parsed.error_message
                                if status
                                in {
                                    ObservationStatus.WAIT_AVAILABLE,
                                    ObservationStatus.NO_WAIT,
                                }
                                and parsed.status is ObservationStatus.PARSE_ERROR
                                else None
                            ),
                        ),
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid manual CSV row {line_number}: {exc}") from exc
    return rows


def _optional_int(value: str | None) -> int | None:
    return int(value) if value is not None and value.strip() else None


class ManualCsvSource:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def collect(
        self, party_sizes: list[int], scheduled_at_utc: datetime
    ) -> dict[int, SourceObservation]:
        rows = read_manual_csv(self.config.manual_csv_path, self.config.timezone)
        results: dict[int, SourceObservation] = {}
        for party_size in party_sizes:
            candidates = [row for row in rows if row["party_size"] == party_size]
            if candidates:
                latest = max(candidates, key=lambda row: row["observed_at"])
                observed = latest["observed_at"]
                parsed = latest["parsed"]
                assert isinstance(observed, datetime)
                assert isinstance(parsed, ParsedWait)
            else:
                observed = datetime.now(UTC)
                parsed = ParsedWait(
                    status=ObservationStatus.PARSE_ERROR,
                    raw_wait_text="",
                    parser_name="manual-csv-v1",
                    error_message=f"No manual CSV row exists for party size {party_size}.",
                )
            results[party_size] = SourceObservation(
                parsed=parsed,
                source_url=str(self.config.manual_csv_path),
                source_provider="manual-csv",
                observed_at_utc=observed.astimezone(UTC),
            )
        return results
