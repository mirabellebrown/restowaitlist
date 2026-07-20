from __future__ import annotations

import hashlib
import re
from html import escape

from bs4 import BeautifulSoup

from dtf_waitwatch.models import ObservationStatus, ParsedWait

PARSER_NAME = "visible-wait-v1"
MAX_STORED_TEXT = 2000
SPACE_RE = re.compile(r"\s+")
RANGE_RE = re.compile(
    r"\b(?P<low>\d{1,3})\s*(?:-|\u2013|\u2014)\s*(?P<high>\d{1,3})\s*"
    r"(?:min(?:ute)?s?)\b",
    re.IGNORECASE,
)
OPEN_ENDED_RE = re.compile(r"\b(?P<low>\d{1,3})\s*\+\s*(?:min(?:ute)?s?)\b", re.IGNORECASE)
SINGLE_RE = re.compile(
    r"\b(?:about\s+|approximately\s+|approx\.?\s+)?(?P<value>\d{1,3})\s*"
    r"(?:min(?:ute)?s?)\b",
    re.IGNORECASE,
)


def sanitize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()[:MAX_STORED_TEXT]


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def parse_wait_text(value: str) -> ParsedWait:
    raw = sanitize_text(value)
    hashed = content_hash(raw)
    lowered = raw.casefold()
    if not raw:
        return ParsedWait(
            status=ObservationStatus.PARSE_ERROR,
            raw_wait_text="",
            content_hash=hashed,
            parser_name=PARSER_NAME,
            error_message="The configured element contained no visible wait text.",
        )
    if re.search(r"\b(no wait|walk right in)\b", lowered):
        return ParsedWait(
            status=ObservationStatus.NO_WAIT,
            wait_min_minutes=0,
            wait_max_minutes=0,
            wait_midpoint_minutes=0,
            raw_wait_text=raw,
            content_hash=hashed,
            parser_name=PARSER_NAME,
        )
    if re.search(r"\b(waitlist|restaurant)\s+(?:is\s+)?closed\b", lowered):
        status = (
            ObservationStatus.RESTAURANT_CLOSED
            if "restaurant" in lowered
            else ObservationStatus.WAITLIST_CLOSED
        )
        return ParsedWait(
            status=status,
            raw_wait_text=raw,
            content_hash=hashed,
            parser_name=PARSER_NAME,
        )
    if re.search(r"\b(waitlist\s+)?(?:temporarily\s+)?unavailable\b", lowered):
        return ParsedWait(
            status=ObservationStatus.TEMPORARILY_UNAVAILABLE,
            raw_wait_text=raw,
            content_hash=hashed,
            parser_name=PARSER_NAME,
        )
    match = RANGE_RE.search(raw)
    if match:
        low, high = int(match.group("low")), int(match.group("high"))
        if high < low:
            return ParsedWait(
                status=ObservationStatus.PARSE_ERROR,
                raw_wait_text=raw,
                content_hash=hashed,
                parser_name=PARSER_NAME,
                error_message="Wait range upper bound is below its lower bound.",
            )
        return ParsedWait(
            status=ObservationStatus.WAIT_AVAILABLE,
            wait_min_minutes=low,
            wait_max_minutes=high,
            wait_midpoint_minutes=(low + high) / 2,
            raw_wait_text=raw,
            content_hash=hashed,
            parser_name=PARSER_NAME,
        )
    match = OPEN_ENDED_RE.search(raw)
    if match:
        low = int(match.group("low"))
        return ParsedWait(
            status=ObservationStatus.WAIT_AVAILABLE,
            wait_min_minutes=low,
            wait_max_minutes=None,
            wait_midpoint_minutes=float(low),
            wait_is_open_ended=True,
            raw_wait_text=raw,
            content_hash=hashed,
            parser_name=PARSER_NAME,
        )
    match = SINGLE_RE.search(raw)
    if match:
        value_minutes = int(match.group("value"))
        return ParsedWait(
            status=ObservationStatus.WAIT_AVAILABLE,
            wait_min_minutes=value_minutes,
            wait_max_minutes=value_minutes,
            wait_midpoint_minutes=float(value_minutes),
            raw_wait_text=raw,
            content_hash=hashed,
            parser_name=PARSER_NAME,
        )
    return ParsedWait(
        status=ObservationStatus.PARSE_ERROR,
        raw_wait_text=raw,
        content_hash=hashed,
        parser_name=PARSER_NAME,
        error_message="No current wait estimate was recognized in the configured element.",
    )


def parse_wait_html(html: str, selector: str, attribute: str | None = None) -> ParsedWait:
    soup = BeautifulSoup(html, "html.parser")
    try:
        element = soup.select_one(selector)
    except Exception as exc:
        return ParsedWait(
            status=ObservationStatus.PARSE_ERROR,
            raw_wait_text="",
            content_hash=content_hash(""),
            parser_name=PARSER_NAME,
            error_message=f"Invalid configured selector: {exc}",
        )
    if element is None:
        return ParsedWait(
            status=ObservationStatus.PARSE_ERROR,
            raw_wait_text="",
            content_hash=content_hash(""),
            parser_name=PARSER_NAME,
            error_message=f"Configured selector did not match: {selector}",
        )
    if attribute:
        value = element.get(attribute, "")
        text = " ".join(value) if isinstance(value, list) else str(value)
    else:
        text = element.get_text(" ", strip=True)
    parsed = parse_wait_text(text)
    if parsed.status is ObservationStatus.PARSE_ERROR and parsed.raw_wait_text:
        # This is a short, sanitized fragment of only the selected node, never the whole page.
        fragment = sanitize_text(str(element))
        return ParsedWait(
            status=parsed.status,
            raw_wait_text=fragment,
            content_hash=content_hash(fragment),
            parser_name=parsed.parser_name,
            error_message=parsed.error_message,
        )
    return parsed


def short_safe_fragment(text: str) -> str:
    """Escape a short diagnostic string for safe report display."""
    return escape(sanitize_text(text))
