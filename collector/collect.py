#!/usr/bin/env python3
"""Local Din Tai Fung Yelp-waitlist collector for RestoWaitlist.

Runs a real, headful Chrome via patchright to read the *publicly displayed*
estimated wait for several party sizes, then POSTs each reading to the
RestoWaitlist API (`POST /api/collect/<slug>`), which stores it in the same
Cloudflare D1 database the dashboard renders from.

Design notes
------------
* It only READS the visible wait estimate — the same number a person sees when
  they open the page. It never logs in, never clicks Join/Confirm, and never
  submits the waitlist form.
* Yelp fronts the page with DataDome. A genuine local browser on a residential
  IP passes DataDome's transparent challenge; automation-flavoured headless
  browsers do not. So this runs headful, from your own machine, on a gentle
  schedule (every 15 min), reusing one warmed browser profile per run.
* If the source blocks a request (HTTP 403/429 or a challenge page), the run
  records `source_blocked`, stops early (no hammering), and simply tries again
  on the next scheduled cycle.

Configuration is entirely via environment variables — see collector/.env.example.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Reuse the canonical wait parser that ships with the dtf_waitwatch package.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from dtf_waitwatch.parsing import parse_wait_text  # noqa: E402


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


SLUG = _env("RWL_SLUG", "din-tai-fung-new-york-3")
API_BASE = (_env("RWL_API_BASE", "http://127.0.0.1:8787") or "").rstrip("/")
TOKEN = _env("RWL_COLLECTOR_TOKEN", "")
WAIT_URL_TEMPLATE = _env(
    "RWL_WAIT_URL",
    "https://www.yelp.com/waitlist/din-tai-fung-new-york-3?party_size={size}",
)
# Warm-up navigation is opt-in: the proven-good path is a direct, cold load of
# the waitlist page from a residential IP. Set RWL_WARMUP_URL to enable it.
WARMUP_URL = _env("RWL_WARMUP_URL", "")
PARTY_SIZES = [int(s) for s in (_env("RWL_PARTY_SIZES", "2,3,4,5") or "").split(",") if s.strip()]
PROFILE_DIR = _env("RWL_PROFILE_DIR", str(Path.home() / ".restowaitlist" / "chrome-profile"))
HEADLESS = (_env("RWL_HEADLESS", "false") or "").lower() in ("1", "true", "yes")
DRY_RUN = (_env("RWL_DRY_RUN", "false") or "").lower() in ("1", "true", "yes")
NAV_TIMEOUT_MS = int(_env("RWL_NAV_TIMEOUT_MS", "45000") or "45000")

# Markers that only appear on a DataDome interstitial / challenge, never on the
# real waitlist widget (which always contains "waitstatus").
BLOCK_MARKERS = (
    "verify you are human",
    "are you a robot",
    "enable js and disable",
    "unusual traffic",
    "access denied",
    "captcha-delivery",
)


def _status_str(status) -> str:
    return getattr(status, "value", str(status))


def bucket_15min_iso(now: datetime) -> str:
    """Floor a UTC timestamp to its 15-minute slot as an ISO-8601 'Z' string.

    Bucketing gives a clean grid and makes re-runs idempotent: the API's
    unique (restaurant, party_size, observed_at) constraint dedupes a slot.
    """
    now = now.astimezone(timezone.utc)
    floored = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    return floored.isoformat().replace("+00:00", "Z")


def extract_wait_text(page) -> str:
    """Read the visible wait value, resilient to Yelp's hashed class names."""
    for selector in ("span[class*='waitstatus-waittime']", "[class*='waitstatus-waittime']"):
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                text = locator.inner_text(timeout=2000).strip()
                if text:
                    return text
        except Exception:
            pass
    try:
        body = page.inner_text("body")
    except Exception:
        return ""
    match = re.search(r"wait\s*time:?\s*([^\n]+)", body, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def looks_blocked(page, status_code) -> bool:
    if status_code in (401, 403, 429):
        return True
    try:
        html = page.content()[:20000].casefold()
    except Exception:
        return False
    if "waitstatus" in html:
        return False
    return any(marker in html for marker in BLOCK_MARKERS)


def _obs(size, observed_iso, status, wait_min, wait_max, raw_text, code, dur, err):
    return {
        "partySize": size,
        "observedAt": observed_iso,
        "status": status,
        "waitMinMinutes": wait_min,
        "waitMaxMinutes": wait_max,
        "rawWaitText": raw_text,
        "responseStatusCode": code,
        "responseDurationMs": dur,
        "errorMessage": err,
    }


def collect() -> list[dict]:
    from patchright.sync_api import sync_playwright

    observed_iso = bucket_15min_iso(datetime.now(timezone.utc))
    results: list[dict] = []

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=HEADLESS,
            no_viewport=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            # Warm up like a person landing on the business page first; this
            # establishes the DataDome session cookie for the waitlist loads.
            if WARMUP_URL:
                try:
                    page.goto(WARMUP_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    time.sleep(random.uniform(3.0, 6.0))
                except Exception as exc:  # noqa: BLE001
                    print(f"[warmup] {exc}")

            for index, size in enumerate(PARTY_SIZES):
                url = WAIT_URL_TEMPLATE.format(size=size)
                started = time.monotonic()
                status_code = None
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    status_code = response.status if response else None
                    time.sleep(random.uniform(5.0, 8.0))
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass

                    duration = round((time.monotonic() - started) * 1000)
                    if looks_blocked(page, status_code):
                        results.append(
                            _obs(
                                size, observed_iso, "source_blocked", None, None, "",
                                status_code, duration,
                                f"Anti-bot block (HTTP {status_code}). No evasion attempted; "
                                "will retry next cycle.",
                            )
                        )
                        print(f"[size {size}] BLOCKED (HTTP {status_code}) — stopping early")
                        break

                    text = extract_wait_text(page)
                    parsed = parse_wait_text(text)
                    results.append(
                        _obs(
                            size, observed_iso, _status_str(parsed.status),
                            parsed.wait_min_minutes, parsed.wait_max_minutes,
                            parsed.raw_wait_text, status_code, duration, parsed.error_message,
                        )
                    )
                    print(f"[size {size}] {_status_str(parsed.status)} :: {text!r}")
                except Exception as exc:  # noqa: BLE001
                    duration = round((time.monotonic() - started) * 1000)
                    results.append(
                        _obs(size, observed_iso, "network_error", None, None, "",
                             status_code, duration, str(exc)[:500])
                    )
                    print(f"[size {size}] ERROR {exc}")

                if index < len(PARTY_SIZES) - 1:
                    time.sleep(random.uniform(4.0, 9.0))
        finally:
            ctx.close()
    return results


def post_results(results: list[dict]) -> bool:
    payload = json.dumps({"observations": results}).encode("utf-8")
    url = f"{API_BASE}/api/collect/{SLUG}"
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            print(f"[api] {response.status} {body[:400]}")
            return True
    except urllib.error.HTTPError as exc:
        print(f"[api] HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:400]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[api] error {exc}")
    return False


def main() -> int:
    if not PARTY_SIZES:
        print("No party sizes configured (RWL_PARTY_SIZES).")
        return 2
    results = collect()
    print("=== results ===")
    print(json.dumps(results, indent=1))
    if DRY_RUN:
        print("[dry-run] not posting to API")
        return 0
    if not TOKEN:
        print("[api] RWL_COLLECTOR_TOKEN is not set; skipping POST.")
        return 0
    return 0 if post_results(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
