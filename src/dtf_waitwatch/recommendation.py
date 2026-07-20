from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.database import Database
from dtf_waitwatch.models import Recommendation

VALID_STATUSES = {"wait_available", "no_wait"}


class InsufficientDataError(ValueError):
    """No meaningful historical observations are available."""


def weighted_quantile(values: list[float], weights: list[float], quantile: float) -> float:
    if len(values) != len(weights) or not values:
        raise ValueError("values and weights must be non-empty and have equal length")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    if any(weight < 0 for weight in weights) or sum(weights) <= 0:
        raise ValueError("weights must be non-negative with a positive total")
    ordered = sorted(zip(values, weights, strict=True), key=lambda pair: pair[0])
    threshold = quantile * sum(weights)
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return float(value)
    return float(ordered[-1][0])


def parse_target(value: str, timezone: Any, now: datetime | None = None) -> datetime:
    normalized = " ".join(value.strip().split())
    lowered = normalized.casefold()
    if lowered.startswith("next "):
        parts = normalized.split()
        if len(parts) != 3:
            raise ValueError("Natural targets must look like 'next Saturday 19:00'")
        weekday_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        try:
            target_weekday = weekday_names.index(parts[1].casefold())
            target_time = time.fromisoformat(parts[2])
        except ValueError as exc:
            raise ValueError(f"Invalid natural target: {value}") from exc
        local_now = (now or datetime.now(UTC)).astimezone(timezone)
        days_ahead = (target_weekday - local_now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return datetime.combine(
            local_now.date() + timedelta(days=days_ahead), target_time, timezone
        )
    parsed = datetime.fromisoformat(normalized)
    return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed.astimezone(timezone)


def recommend(
    *,
    database: Database,
    config: AppConfig,
    location_id: int,
    target_local: datetime,
    party_size: int,
    risk: float,
) -> Recommendation:
    if not 0.5 <= risk <= 0.99:
        raise ValueError("risk must be between 0.50 and 0.99")
    if target_local.tzinfo is None:
        target_local = target_local.replace(tzinfo=config.timezone)
    else:
        target_local = target_local.astimezone(config.timezone)
    rows = database.list_observations(location_id, party_size)
    warnings: list[str] = []
    if not rows:
        rows = database.list_observations(location_id)
        if rows:
            warnings.append(
                f"No observations exist for party size {party_size}; all party sizes were used."
            )
    samples = _prepare_samples(rows, config)
    if not samples:
        raise InsufficientDataError("No valid wait observations are available for recommendation.")

    calibration = _calibration_minutes(database, location_id, party_size)
    candidates = [
        target_local - timedelta(hours=4) + timedelta(minutes=15 * index) for index in range(17)
    ]
    open_candidates = [candidate for candidate in candidates if config.is_open(candidate)]
    if not open_candidates:
        opening = config.opening_time(target_local.date())
        if opening and opening <= target_local:
            open_candidates = [opening]
        else:
            raise InsufficientDataError(
                "No candidate join time falls within configured opening hours."
            )

    evaluations: list[tuple[datetime, dict[str, Any]]] = []
    for candidate in open_candidates:
        comparable, fallback = _comparable_samples(samples, candidate)
        if not comparable:
            continue
        evaluation = _evaluate(comparable, candidate, risk, calibration)
        evaluation["fallback"] = fallback
        evaluations.append((candidate, evaluation))
    if not evaluations:
        raise InsufficientDataError(
            "No observations are within 60 minutes of candidate join times."
        )

    satisfying = [
        item
        for item in evaluations
        if item[0] + timedelta(minutes=item[1]["risk_wait"]) <= target_local
    ]
    if satisfying:
        candidate, selected = max(satisfying, key=lambda item: item[0])
    else:
        candidate, selected = min(evaluations, key=lambda item: item[0])
        warnings.append(
            "No evaluated candidate satisfies the requested risk threshold; returning the earliest "
            "candidate."
        )

    independent_dates = len({sample["local"].date() for sample in selected["samples"]})
    confidence = _confidence(independent_dates, selected["conservative_values"])
    if independent_dates < 3:
        warnings.append("Fewer than three comparable independent dates are available.")
    if selected["fallback"] != "same_weekday":
        warnings.append(
            "Same-weekday history was insufficient; the documented fallback hierarchy was used."
        )
    if any(sample["open_ended"] for sample in selected["samples"]):
        warnings.append(
            "Open-ended estimates use their lower bound because no displayed upper bound exists."
        )
    closed_fraction = _closed_fraction(rows, candidate, config)
    if closed_fraction >= 0.20:
        warnings.append(
            f"The waitlist was closed or unavailable in {closed_fraction:.0%} of nearby status "
            "observations."
        )
    dates = sorted(sample["local"].date() for sample in selected["samples"])
    p50 = selected["p50"]
    risk_wait = selected["risk_wait"]
    return Recommendation(
        target_local=target_local,
        recommended_join_local=candidate,
        risk=risk,
        p50_minutes=p50,
        p80_minutes=selected["p80"],
        p90_minutes=selected["p90"],
        risk_wait_minutes=risk_wait,
        expected_ready_start_local=candidate + timedelta(minutes=p50),
        expected_ready_end_local=candidate + timedelta(minutes=risk_wait),
        observation_count=len(selected["samples"]),
        independent_dates=independent_dates,
        data_start=dates[0].isoformat() if dates else None,
        data_end=dates[-1].isoformat() if dates else None,
        confidence=confidence,
        fallback_level=selected["fallback"],
        calibration_minutes=calibration,
        closed_fraction=closed_fraction,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _prepare_samples(rows: list[Any], config: AppConfig) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        if row["status"] not in VALID_STATUSES or row["wait_midpoint_minutes"] is None:
            continue
        scheduled = datetime.fromisoformat(row["scheduled_at_utc"]).astimezone(config.timezone)
        if config.opening_hours and not config.is_open(scheduled):
            continue
        conservative = (
            float(row["wait_max_minutes"])
            if row["wait_max_minutes"] is not None
            else float(row["wait_min_minutes"] or 0)
        )
        samples.append(
            {
                "local": scheduled,
                "midpoint": float(row["wait_midpoint_minutes"]),
                "conservative": conservative,
                "open_ended": bool(row["wait_is_open_ended"]),
            }
        )
    return samples


def _minute_distance(first: datetime, second: datetime) -> float:
    first_minutes = first.hour * 60 + first.minute
    second_minutes = second.hour * 60 + second.minute
    return abs(first_minutes - second_minutes)


def _comparable_samples(
    samples: list[dict[str, Any]], candidate: datetime
) -> tuple[list[dict[str, Any]], str]:
    nearby = [sample for sample in samples if _minute_distance(sample["local"], candidate) <= 60]
    same_weekday = [sample for sample in nearby if sample["local"].weekday() == candidate.weekday()]
    if len({sample["local"].date() for sample in same_weekday}) >= 3:
        return same_weekday, "same_weekday"
    same_category = [
        sample
        for sample in nearby
        if (sample["local"].weekday() >= 5) == (candidate.weekday() >= 5)
    ]
    if len({sample["local"].date() for sample in same_category}) >= 3:
        return same_category, "weekday_or_weekend"
    return nearby, "all_days_nearby_time"


def _date_balanced_weights(samples: list[dict[str, Any]], candidate: datetime) -> list[float]:
    raw = [1 / (1 + _minute_distance(sample["local"], candidate) / 15) for sample in samples]
    totals: defaultdict[date, float] = defaultdict(float)
    for sample, weight in zip(samples, raw, strict=True):
        totals[sample["local"].date()] += weight
    return [
        weight / totals[sample["local"].date()] for sample, weight in zip(samples, raw, strict=True)
    ]


def _evaluate(
    samples: list[dict[str, Any]], candidate: datetime, risk: float, calibration: float | None
) -> dict[str, Any]:
    weights = _date_balanced_weights(samples, candidate)
    adjustment = calibration or 0.0
    midpoint_values = [max(0.0, sample["midpoint"] + adjustment) for sample in samples]
    conservative = [max(0.0, sample["conservative"] + adjustment) for sample in samples]
    return {
        "samples": samples,
        "conservative_values": conservative,
        "p50": weighted_quantile(midpoint_values, weights, 0.50),
        "p80": weighted_quantile(conservative, weights, 0.80),
        "p90": weighted_quantile(conservative, weights, 0.90),
        "risk_wait": weighted_quantile(conservative, weights, risk),
    }


def _calibration_minutes(database: Database, location_id: int, party_size: int) -> float | None:
    differences: list[float] = []
    for row in database.list_actual_waits(location_id, party_size):
        low, high = row["displayed_wait_min_minutes"], row["displayed_wait_max_minutes"]
        if low is None and high is None:
            continue
        displayed = ((low or high) + (high or low)) / 2
        differences.append(float(row["actual_wait_minutes"]) - displayed)
    if not differences:
        return None
    return max(-30.0, min(60.0, statistics.median(differences)))


def _confidence(independent_dates: int, values: list[float]) -> str:
    if independent_dates < 2:
        return "very low"
    if independent_dates <= 3:
        return "low"
    if independent_dates <= 7:
        return "medium"
    mean = statistics.fmean(values) if values else 0
    variation = statistics.pstdev(values) / mean if mean else math.inf
    return "high" if variation <= 0.5 else "medium"


def _closed_fraction(rows: list[Any], candidate: datetime, config: AppConfig) -> float:
    nearby = []
    for row in rows:
        scheduled = datetime.fromisoformat(row["scheduled_at_utc"]).astimezone(config.timezone)
        if _minute_distance(scheduled, candidate) <= 60:
            nearby.append(row["status"])
    if not nearby:
        return 0.0
    closed = sum(
        status in {"waitlist_closed", "temporarily_unavailable", "source_blocked"}
        for status in nearby
    )
    return closed / len(nearby)
