from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class ObservationStatus(StrEnum):
    WAIT_AVAILABLE = "wait_available"
    NO_WAIT = "no_wait"
    WAITLIST_CLOSED = "waitlist_closed"
    RESTAURANT_CLOSED = "restaurant_closed"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    SOURCE_BLOCKED = "source_blocked"
    PARSE_ERROR = "parse_error"
    NETWORK_ERROR = "network_error"
    MISSED_DUE_TO_DOWNTIME = "missed_due_to_downtime"


class SourceType(StrEnum):
    HTTP = "http"
    PLAYWRIGHT = "playwright"
    MANUAL = "manual"
    DEMO = "demo"


@dataclass(frozen=True, slots=True)
class ParsedWait:
    status: ObservationStatus
    raw_wait_text: str
    wait_min_minutes: int | None = None
    wait_max_minutes: int | None = None
    wait_midpoint_minutes: float | None = None
    wait_is_open_ended: bool = False
    content_hash: str | None = None
    parser_name: str = "visible-wait-v1"
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class SourceObservation:
    parsed: ParsedWait
    source_url: str
    source_provider: str
    response_status_code: int | None = None
    response_duration_ms: int | None = None
    observed_at_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class Recommendation:
    target_local: datetime
    recommended_join_local: datetime
    risk: float
    p50_minutes: float
    p80_minutes: float
    p90_minutes: float
    risk_wait_minutes: float
    expected_ready_start_local: datetime
    expected_ready_end_local: datetime
    observation_count: int
    independent_dates: int
    data_start: str | None
    data_end: str | None
    confidence: str
    fallback_level: str
    calibration_minutes: float | None
    closed_fraction: float
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_local": self.target_local.isoformat(),
            "recommended_join_local": self.recommended_join_local.isoformat(),
            "risk": self.risk,
            "estimated_wait_minutes": {
                "p50": round(self.p50_minutes, 1),
                "p80": round(self.p80_minutes, 1),
                "p90": round(self.p90_minutes, 1),
                "at_requested_risk": round(self.risk_wait_minutes, 1),
            },
            "expected_ready_window": {
                "start": self.expected_ready_start_local.isoformat(),
                "end": self.expected_ready_end_local.isoformat(),
            },
            "samples": {
                "observations": self.observation_count,
                "independent_dates": self.independent_dates,
                "data_start": self.data_start,
                "data_end": self.data_end,
            },
            "confidence": self.confidence,
            "fallback_level": self.fallback_level,
            "calibration_minutes": self.calibration_minutes,
            "closed_fraction": round(self.closed_fraction, 3),
            "warnings": list(self.warnings),
        }
