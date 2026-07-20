# RestoWaitlist collector

A small local agent that reads Din Tai Fung's **publicly displayed** Yelp
waitlist estimate for several party sizes and publishes each reading to
**her repo's `gh-pages` branch** (`mirabellebrown/restowaitlist` →
`data/waits.json`), and mirrors the same commit to the fork so the public
dashboard at https://jdelpego.github.io/restowaitlist/ stays live.

Optionally, the same readings can also be POSTed to her Cloudflare Worker
(`/api/collect/<slug>`) if that is deployed later.

It reads the visible number only. It never signs in, never clicks
Join/Confirm, and never submits the waitlist form.

## Why it runs locally (and headful)

Yelp fronts the waitlist page with DataDome bot protection. A genuine, headful
Chrome on a residential IP passes DataDome's transparent challenge; headless or
datacenter browsers get a `403` challenge page. So the collector runs on your
Mac, in a real Chrome window, on a gentle schedule. If a request is blocked it
records `source_blocked` and retries next cycle — it never bursts.

**Do not rapid-test against Yelp.** A burst of ~10 requests can cooldown the
home IP for an hour+. Production pace is ~4 party sizes every 15 minutes.

## One-time setup

```bash
cd collector
python3.12 -m venv .venv           # or: uv venv --python 3.12 .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env               # then edit .env (see below)

# Local checkout the collector publishes into:
git clone --branch gh-pages https://github.com/jdelpego/restowaitlist.git \
  ~/.restowaitlist/site
```

Chrome itself is reused from `/Applications/Google Chrome.app` (the collector
launches `channel="chrome"`), so there is no separate browser download.

### Optional: seed DataDome from your main Chrome profile

If you already have the Yelp waitlist page open and verified in Chrome:

```bash
.venv/bin/python import_yelp_cookie.py
```

macOS will prompt once for Keychain access to "Chrome Safe Storage". Only the
`datadome` cookie for yelp.com is exported.

### Edit `.env`

| Variable | Purpose |
|---|---|
| `RWL_SITE_DIR` | Path to the local `gh-pages` checkout (required for Pages publish) |
| `RWL_PARTY_SIZES` | Defaults to `2,3,4,5` (5 = Yelp's "5+") |
| `RWL_COOKIE_FILE` | Optional path to exported datadome cookie JSON |
| `RWL_API_BASE` / `RWL_COLLECTOR_TOKEN` | Optional Cloudflare POST; leave blank for Pages-only |

## Run it

```bash
# scrape + print, without publishing (still fetches Yelp — use sparingly):
RWL_DRY_RUN=true ./run.sh
# real run (merges into gh-pages data/waits.json and pushes):
./run.sh
```

## Schedule every 15 minutes (macOS launchd)

Runs at :00/:15/:30/:45 from **11:00–23:45 ET** only (quiet midnight–11am).
The LaunchAgent uses local clock hours; `collect.py` also enforces the same
window in `America/New_York` so overnight scrapes cannot slip through.

```bash
cp com.restowaitlist.collector.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.restowaitlist.collector 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.restowaitlist.collector.plist
# logs: ~/.restowaitlist/collector.log and collector.err.log
# to stop: launchctl bootout gui/$(id -u)/com.restowaitlist.collector
```

Each cycle warms one Chrome profile, reads the configured party sizes with
human-like pauses, and publishes one batch. Readings are bucketed to the
15-minute slot so re-runs are idempotent.

## Hosted dashboard

- **Live URL:** https://jdelpego.github.io/restowaitlist/
- **Source of truth:** https://github.com/mirabellebrown/restowaitlist/tree/gh-pages
- **Data:** `gh-pages` → `data/waits.json` (archive only; no raw table in the UI)
- **UI:** her chart + latest-reading card + party picker
- Local checkout (`RWL_SITE_DIR`) should have `origin` → her repo and `mirror` → fork
