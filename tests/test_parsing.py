from pathlib import Path

import pytest

from dtf_waitwatch.models import ObservationStatus
from dtf_waitwatch.parsing import parse_wait_html, parse_wait_text


@pytest.mark.parametrize(
    ("text", "status", "low", "high", "midpoint", "open_ended"),
    [
        ("70-90 mins", ObservationStatus.WAIT_AVAILABLE, 70, 90, 80, False),
        ("70 – 90 minutes", ObservationStatus.WAIT_AVAILABLE, 70, 90, 80, False),
        ("About 45 minutes", ObservationStatus.WAIT_AVAILABLE, 45, 45, 45, False),
        ("45 min", ObservationStatus.WAIT_AVAILABLE, 45, 45, 45, False),
        ("90+ minutes", ObservationStatus.WAIT_AVAILABLE, 90, None, 90, True),
        ("No wait", ObservationStatus.NO_WAIT, 0, 0, 0, False),
        ("Walk right in", ObservationStatus.NO_WAIT, 0, 0, 0, False),
        ("Waitlist closed", ObservationStatus.WAITLIST_CLOSED, None, None, None, False),
        (
            "Waitlist unavailable",
            ObservationStatus.TEMPORARILY_UNAVAILABLE,
            None,
            None,
            None,
            False,
        ),
    ],
)
def test_all_documented_wait_formats(text, status, low, high, midpoint, open_ended):
    parsed = parse_wait_text(text)
    assert parsed.status is status
    assert parsed.wait_min_minutes == low
    assert parsed.wait_max_minutes == high
    assert parsed.wait_midpoint_minutes == midpoint
    assert parsed.wait_is_open_ended is open_ended


@pytest.mark.parametrize(
    ("fixture", "status"),
    [
        ("wait_range.html", ObservationStatus.WAIT_AVAILABLE),
        ("no_wait.html", ObservationStatus.NO_WAIT),
        ("closed.html", ObservationStatus.WAITLIST_CLOSED),
        ("unavailable.html", ObservationStatus.TEMPORARILY_UNAVAILABLE),
    ],
)
def test_synthetic_html_fixtures(fixture, status):
    html = (Path(__file__).parent / "fixtures" / fixture).read_text(encoding="utf-8")
    parsed = parse_wait_html(html, "[data-wait-estimate], .wait-time")
    assert parsed.status is status


def test_does_not_scan_reservation_times_outside_selector():
    html = "<div>Reservation at 7:30, about 45 minutes away</div><span id='wait'>Closed</span>"
    parsed = parse_wait_html(html, "#wait")
    assert parsed.status is ObservationStatus.PARSE_ERROR
    assert "45" not in parsed.raw_wait_text


def test_selected_fragment_is_limited():
    parsed = parse_wait_html(f"<p id='wait'>{'x' * 3000}</p>", "#wait")
    assert len(parsed.raw_wait_text) <= 2000
