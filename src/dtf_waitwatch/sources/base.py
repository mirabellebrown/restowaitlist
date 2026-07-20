from __future__ import annotations

from datetime import datetime
from typing import Protocol

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.models import SourceObservation, SourceType


class PermissionRequiredError(RuntimeError):
    """Automated collection was requested without a stored permission acknowledgment."""


class WaitSource(Protocol):
    def collect(
        self, party_sizes: list[int], scheduled_at_utc: datetime
    ) -> dict[int, SourceObservation]: ...


def require_automation_acknowledgment(config: AppConfig) -> None:
    automated = config.source.type in {SourceType.HTTP, SourceType.PLAYWRIGHT}
    if automated and not config.source.permission_acknowledged:
        raise PermissionRequiredError(
            "Automated collection is disabled. Review the source terms and confirm you have "
            "permission, then set source.permission_acknowledged = true. The acknowledgment "
            "records your review; it does not create permission. Source URL: "
            f"{config.location.wait_source_url}"
        )


def build_source(config: AppConfig) -> WaitSource:
    require_automation_acknowledgment(config)
    if config.source.type is SourceType.HTTP:
        from dtf_waitwatch.sources.authorized_http import AuthorizedHttpSource

        return AuthorizedHttpSource(config)
    if config.source.type is SourceType.PLAYWRIGHT:
        from dtf_waitwatch.sources.authorized_playwright import AuthorizedPlaywrightSource

        return AuthorizedPlaywrightSource(config)
    if config.source.type is SourceType.MANUAL:
        from dtf_waitwatch.sources.manual_csv import ManualCsvSource

        return ManualCsvSource(config)
    from dtf_waitwatch.sources.demo import DemoSource

    return DemoSource(config)
