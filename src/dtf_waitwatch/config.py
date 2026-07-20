from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dtf_waitwatch.models import SourceType

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DEFAULT_SELECTOR = "[data-wait-estimate], .wait-time, .wait-estimate"
DEFAULT_USER_AGENT = "dtf-waitwatch/0.1 (permission-aware personal monitoring)"


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


@dataclass(slots=True)
class LocationConfig:
    name: str
    timezone: str
    official_url: str
    wait_source_url: str
    provider: str = "generic"
    address: str | None = None


@dataclass(slots=True)
class SourceConfig:
    type: SourceType
    permission_acknowledged: bool = False
    permission_reviewed_at: str | None = None
    selector: str = DEFAULT_SELECTOR
    attribute: str | None = None
    manual_csv_path: str = "./data/manual-waits.csv"
    timeout_seconds: float = 20.0
    transient_retry_delay_seconds: float = 1.0
    user_agent: str = DEFAULT_USER_AGENT


@dataclass(slots=True)
class CollectionConfig:
    party_sizes: list[int] = field(default_factory=lambda: [2])
    duration_days: float = 5.0
    interval_minutes: int = 15


@dataclass(slots=True)
class RecommendationConfig:
    default_risk_percentile: float = 0.80


@dataclass(slots=True)
class DatabaseConfig:
    path: str = "./data/waits.sqlite3"


@dataclass(slots=True)
class AppConfig:
    location: LocationConfig
    source: SourceConfig
    collection: CollectionConfig = field(default_factory=CollectionConfig)
    recommendation: RecommendationConfig = field(default_factory=RecommendationConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    opening_hours: dict[str, list[str]] = field(default_factory=dict)
    config_path: Path = field(default=Path("config.toml"), repr=False)

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.location.timezone)

    @property
    def database_path(self) -> Path:
        raw = Path(self.database.path)
        return raw if raw.is_absolute() else (self.config_path.parent / raw).resolve()

    @property
    def manual_csv_path(self) -> Path:
        raw = Path(self.source.manual_csv_path)
        return raw if raw.is_absolute() else (self.config_path.parent / raw).resolve()

    def is_open(self, local_dt: datetime) -> bool:
        periods = self.opening_hours.get(WEEKDAYS[local_dt.weekday()])
        if not periods:
            return not self.opening_hours
        local_t = local_dt.timetz().replace(tzinfo=None)
        for period in periods:
            start_text, end_text = period.split("-", maxsplit=1)
            start, end = time.fromisoformat(start_text), time.fromisoformat(end_text)
            if start <= end and start <= local_t < end:
                return True
            if start > end and (local_t >= start or local_t < end):
                return True
        return False

    def opening_time(self, day: date) -> datetime | None:
        periods = self.opening_hours.get(WEEKDAYS[day.weekday()])
        if not periods:
            return None
        start_text = periods[0].split("-", maxsplit=1)[0]
        return datetime.combine(day, time.fromisoformat(start_text), self.timezone)


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a TOML table")
    return value


def load_config(path: str | Path = "config.toml") -> AppConfig:
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    location = _table(data, "location")
    source = _table(data, "source")
    collection = _table(data, "collection")
    recommendation = _table(data, "recommendation")
    database = _table(data, "database")
    try:
        config = AppConfig(
            location=LocationConfig(
                name=str(location["name"]),
                address=location.get("address") or None,
                timezone=str(location["timezone"]),
                official_url=str(location.get("official_url", "")),
                wait_source_url=str(location.get("wait_source_url", "")),
                provider=str(location.get("provider", "generic")),
            ),
            source=SourceConfig(
                type=SourceType(str(source["type"]).lower()),
                permission_acknowledged=bool(source.get("permission_acknowledged", False)),
                permission_reviewed_at=source.get("permission_reviewed_at") or None,
                selector=str(source.get("selector", DEFAULT_SELECTOR)),
                attribute=source.get("attribute") or None,
                manual_csv_path=str(source.get("manual_csv_path", "./data/manual-waits.csv")),
                timeout_seconds=float(source.get("timeout_seconds", 20.0)),
                transient_retry_delay_seconds=float(
                    source.get("transient_retry_delay_seconds", 1.0)
                ),
                user_agent=str(source.get("user_agent", DEFAULT_USER_AGENT)),
            ),
            collection=CollectionConfig(
                party_sizes=[int(value) for value in collection.get("party_sizes", [2])],
                duration_days=float(collection.get("duration_days", 5.0)),
                interval_minutes=int(collection.get("interval_minutes", 15)),
            ),
            recommendation=RecommendationConfig(
                default_risk_percentile=float(recommendation.get("default_risk_percentile", 0.80))
            ),
            database=DatabaseConfig(path=str(database.get("path", "./data/waits.sqlite3"))),
            opening_hours={
                str(day).lower(): [str(period) for period in periods]
                for day, periods in _table(data, "opening_hours").items()
            },
            config_path=config_path,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    errors: list[str] = []
    if not config.location.name.strip():
        errors.append("location.name is required")
    try:
        ZoneInfo(config.location.timezone)
    except ZoneInfoNotFoundError:
        errors.append(f"unknown IANA timezone: {config.location.timezone}")
    if config.source.type in {SourceType.HTTP, SourceType.PLAYWRIGHT}:
        if not config.location.wait_source_url.startswith(("http://", "https://")):
            errors.append("automated sources require an http(s) wait_source_url")
        if not config.source.selector.strip():
            errors.append("automated sources require source.selector")
        if len(config.collection.party_sizes) != 1:
            errors.append(
                "automated sources currently require exactly one party size so that only one page "
                "is loaded per interval"
            )
    if not config.collection.party_sizes or any(size < 1 for size in config.collection.party_sizes):
        errors.append("collection.party_sizes must contain positive integers")
    if config.collection.duration_days <= 0:
        errors.append("collection.duration_days must be positive")
    if config.collection.interval_minutes <= 0:
        errors.append("collection.interval_minutes must be positive")
    risk = config.recommendation.default_risk_percentile
    if not 0.5 <= risk <= 0.99:
        errors.append("recommendation.default_risk_percentile must be between 0.50 and 0.99")
    for day, periods in config.opening_hours.items():
        if day not in WEEKDAYS:
            errors.append(f"unknown weekday in opening_hours: {day}")
        for period in periods:
            try:
                start_text, end_text = period.split("-", maxsplit=1)
                time.fromisoformat(start_text)
                time.fromisoformat(end_text)
            except (ValueError, TypeError):
                errors.append(f"invalid opening period for {day}: {period!r}")
    if errors:
        raise ConfigError("; ".join(errors))
