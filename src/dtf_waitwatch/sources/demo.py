from __future__ import annotations

import math
from datetime import datetime

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.models import SourceObservation
from dtf_waitwatch.parsing import parse_wait_text


class DemoSource:
    """Deterministic synthetic source. Its values must never be treated as real observations."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def collect(
        self, party_sizes: list[int], scheduled_at_utc: datetime
    ) -> dict[int, SourceObservation]:
        local = scheduled_at_utc.astimezone(self.config.timezone)
        results: dict[int, SourceObservation] = {}
        for party_size in party_sizes:
            hour = local.hour + local.minute / 60
            dinner_peak = 70 * math.exp(-((hour - 19.25) ** 2) / 2.2)
            lunch_peak = 28 * math.exp(-((hour - 13.0) ** 2) / 1.5)
            weekend = 20 if local.weekday() >= 5 else 0
            deterministic_variation = ((local.toordinal() * 7 + party_size * 11) % 17) - 8
            midpoint = max(
                0, round((dinner_peak + lunch_peak + weekend + deterministic_variation) / 5) * 5
            )
            spread = 10 if midpoint >= 20 else 0
            low, high = max(0, midpoint - spread), midpoint + spread
            text = "No wait" if high == 0 else f"{low}-{high} mins"
            results[party_size] = SourceObservation(
                parsed=parse_wait_text(text),
                source_url="demo://synthetic-wait-estimates",
                source_provider="synthetic-demo",
                observed_at_utc=scheduled_at_utc,
            )
        return results
