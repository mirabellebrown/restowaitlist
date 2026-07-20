from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.models import ObservationStatus, ParsedWait, SourceObservation
from dtf_waitwatch.parsing import parse_wait_text
from dtf_waitwatch.sources.base import require_automation_acknowledgment


class AuthorizedPlaywrightSource:
    """Read one configured visible element; never clicks, logs in, or submits a form."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def collect(
        self, party_sizes: list[int], scheduled_at_utc: datetime
    ) -> dict[int, SourceObservation]:
        require_automation_acknowledgment(self.config)
        if len(party_sizes) != 1:
            raise ValueError("Playwright collection supports one party size per page load")
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is optional. Install with 'pip install -e .[browser]' and run "
                "'playwright install chromium'."
            ) from exc
        started = monotonic()
        status_code: int | None = None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                response = page.goto(
                    self.config.location.wait_source_url,
                    wait_until="domcontentloaded",
                    timeout=round(self.config.source.timeout_seconds * 1000),
                )
                status_code = response.status if response else None
                body_lower = page.content()[:100_000].casefold()
                block_markers = (
                    "captcha",
                    "are you a robot",
                    "verify you are human",
                    "unusual traffic",
                    "access denied",
                    "bot detection",
                )
                if status_code in {401, 403, 429} or any(
                    marker in body_lower for marker in block_markers
                ):
                    parsed = ParsedWait(
                        status=ObservationStatus.SOURCE_BLOCKED,
                        raw_wait_text="",
                        parser_name="playwright-block-detection-v1",
                        error_message=(
                            f"Source blocked automated access (HTTP {status_code}). No evasion or "
                            "further retry was attempted."
                        ),
                    )
                elif status_code is not None and status_code >= 500:
                    parsed = ParsedWait(
                        status=ObservationStatus.TEMPORARILY_UNAVAILABLE,
                        raw_wait_text="",
                        parser_name="playwright-http-status",
                        error_message=f"Source returned HTTP {status_code}.",
                    )
                else:
                    locator = page.locator(self.config.source.selector).first
                    if self.config.source.attribute:
                        text = locator.get_attribute(self.config.source.attribute) or ""
                    else:
                        text = locator.inner_text()
                    parsed = parse_wait_text(text)
                browser.close()
        except PlaywrightTimeoutError as exc:
            parsed = ParsedWait(
                status=ObservationStatus.NETWORK_ERROR,
                raw_wait_text="",
                parser_name="playwright-transport",
                error_message=f"Browser page load timed out: {exc}",
            )
        except PlaywrightError as exc:
            parsed = ParsedWait(
                status=ObservationStatus.PARSE_ERROR,
                raw_wait_text="",
                parser_name="playwright-visible-element",
                error_message=f"Could not read the configured visible wait element: {exc}",
            )
        duration = round((monotonic() - started) * 1000)
        observed = datetime.now(UTC)
        return {
            party_size: SourceObservation(
                parsed=parsed,
                source_url=self.config.location.wait_source_url,
                source_provider=self.config.location.provider,
                response_status_code=status_code,
                response_duration_ms=duration,
                observed_at_utc=observed,
            )
            for party_size in party_sizes
        }
