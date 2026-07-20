from __future__ import annotations

from pathlib import Path

import pytest

from dtf_waitwatch.config import (
    AppConfig,
    CollectionConfig,
    DatabaseConfig,
    LocationConfig,
    RecommendationConfig,
    SourceConfig,
)
from dtf_waitwatch.models import SourceType


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        location=LocationConfig(
            name="Test Restaurant",
            address="1 Test Street",
            timezone="America/New_York",
            official_url="https://example.test/restaurant",
            wait_source_url="https://example.test/waitlist?party_size=2",
            provider="test-provider",
        ),
        source=SourceConfig(
            type=SourceType.DEMO,
            permission_acknowledged=False,
            selector="[data-wait-estimate]",
            manual_csv_path=str(tmp_path / "manual.csv"),
            transient_retry_delay_seconds=0,
        ),
        collection=CollectionConfig(party_sizes=[2], duration_days=5, interval_minutes=15),
        recommendation=RecommendationConfig(default_risk_percentile=0.8),
        database=DatabaseConfig(path=str(tmp_path / "waits.sqlite3")),
        opening_hours={},
        config_path=tmp_path / "config.toml",
    )
