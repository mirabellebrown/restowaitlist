from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.models import ObservationStatus, ParsedWait, SourceObservation
from dtf_waitwatch.parsing import content_hash, parse_wait_html
from dtf_waitwatch.sources.base import require_automation_acknowledgment

BLOCK_MARKERS = (
    "captcha",
    "are you a robot",
    "verify you are human",
    "unusual traffic",
    "access denied",
    "bot detection",
)
BLOCK_STATUS_CODES = {401, 403, 429}


class AuthorizedHttpSource:
    def __init__(self, config: AppConfig, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        self.transport = transport

    def collect(
        self, party_sizes: list[int], scheduled_at_utc: datetime
    ) -> dict[int, SourceObservation]:
        require_automation_acknowledgment(self.config)
        if len(party_sizes) != 1:
            raise ValueError("HTTP collection supports one party size per page load")
        started = time.monotonic()
        response: httpx.Response | None = None
        error: Exception | None = None
        with httpx.Client(
            timeout=self.config.source.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.config.source.user_agent},
            transport=self.transport,
        ) as client:
            for attempt in range(2):
                try:
                    response = client.get(self.config.location.wait_source_url)
                    error = None
                    break
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                    error = exc
                    if attempt == 0:
                        time.sleep(self.config.source.transient_retry_delay_seconds)
        duration = round((time.monotonic() - started) * 1000)
        if error is not None or response is None:
            parsed = ParsedWait(
                status=ObservationStatus.NETWORK_ERROR,
                raw_wait_text="",
                parser_name="transport",
                error_message=f"Network request failed after one retry: {error}",
            )
            return self._same_result(party_sizes, parsed, None, duration)
        body_lower = response.text[:100_000].casefold()
        if response.status_code in BLOCK_STATUS_CODES or any(
            marker in body_lower for marker in BLOCK_MARKERS
        ):
            parsed = ParsedWait(
                status=ObservationStatus.SOURCE_BLOCKED,
                raw_wait_text="",
                content_hash=content_hash("blocked-response"),
                parser_name="block-detection-v1",
                error_message=(
                    f"Source blocked automated access (HTTP {response.status_code}). "
                    "No evasion or further retry was attempted."
                ),
            )
        elif response.status_code >= 500:
            parsed = ParsedWait(
                status=ObservationStatus.TEMPORARILY_UNAVAILABLE,
                raw_wait_text="",
                parser_name="http-status",
                error_message=f"Source returned HTTP {response.status_code}.",
            )
        elif response.is_error:
            parsed = ParsedWait(
                status=ObservationStatus.NETWORK_ERROR,
                raw_wait_text="",
                parser_name="http-status",
                error_message=f"Source returned HTTP {response.status_code}.",
            )
        else:
            parsed = parse_wait_html(
                response.text, self.config.source.selector, self.config.source.attribute
            )
        return self._same_result(party_sizes, parsed, response.status_code, duration)

    def _same_result(
        self,
        party_sizes: list[int],
        parsed: ParsedWait,
        status_code: int | None,
        duration_ms: int,
    ) -> dict[int, SourceObservation]:
        observed = datetime.now(UTC)
        return {
            party_size: SourceObservation(
                parsed=parsed,
                source_url=self.config.location.wait_source_url,
                source_provider=self.config.location.provider,
                response_status_code=status_code,
                response_duration_ms=duration_ms,
                observed_at_utc=observed,
            )
            for party_size in party_sizes
        }
