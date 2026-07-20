from datetime import UTC, datetime

import httpx
import pytest

from dtf_waitwatch.models import ObservationStatus, SourceType
from dtf_waitwatch.sources import PermissionRequiredError
from dtf_waitwatch.sources.authorized_http import AuthorizedHttpSource


def test_http_source_requires_permission_before_request(app_config):
    app_config.source.type = SourceType.HTTP
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<p data-wait-estimate>45 min</p>")

    source = AuthorizedHttpSource(app_config, httpx.MockTransport(handler))
    with pytest.raises(PermissionRequiredError):
        source.collect([2], datetime.now(UTC))
    assert calls == 0


def test_http_source_makes_one_page_load_and_parses(app_config):
    app_config.source.type = SourceType.HTTP
    app_config.source.permission_acknowledged = True
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<p data-wait-estimate>45 min</p>")

    source = AuthorizedHttpSource(app_config, httpx.MockTransport(handler))
    result = source.collect([2], datetime.now(UTC))
    assert calls == 1
    assert result[2].parsed.status is ObservationStatus.WAIT_AVAILABLE


@pytest.mark.parametrize("status", [401, 403, 429])
def test_http_block_status_is_terminal(app_config, status):
    app_config.source.type = SourceType.HTTP
    app_config.source.permission_acknowledged = True
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status, text="blocked")

    result = AuthorizedHttpSource(app_config, httpx.MockTransport(handler)).collect(
        [2], datetime.now(UTC)
    )
    assert calls == 1
    assert result[2].parsed.status is ObservationStatus.SOURCE_BLOCKED
