# RestoWaitlist collector

A small local agent that reads Din Tai Fung's **publicly displayed** Yelp
waitlist estimate for several party sizes and posts each reading to the
RestoWaitlist API, which stores it in the same Cloudflare D1 database the
dashboard renders from. Her manual-entry flow, UI, and existing data are
untouched — this just adds automated readings alongside them.

It reads the visible number only. It never signs in, never clicks
Join/Confirm, and never submits the waitlist form.

## Why it runs locally (and headful)

Yelp fronts the waitlist page with DataDome bot protection. A genuine, headful
Chrome on a residential IP passes DataDome's transparent challenge; headless or
datacenter browsers get a `403` challenge page. So the collector runs on your
Mac, in a real Chrome window, on a gentle schedule. If a request is blocked it
records `source_blocked` and retries next cycle — it never tries to evade.

## One-time setup

```bash
cd collector
python3.12 -m venv .venv           # or: uv venv --python 3.12 .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env               # then edit .env (see below)
```

Chrome itself is reused from `/Applications/Google Chrome.app` (the collector
launches `channel="chrome"`), so there is no separate browser download.

Edit `.env`:

- `RWL_API_BASE` — `http://127.0.0.1:8787` for local preview, or your deployed
  `https://restowaitlist.<subdomain>.workers.dev` in production.
- `RWL_COLLECTOR_TOKEN` — a shared secret; must match the Worker's
  `COLLECTOR_TOKEN` (see below).
- `RWL_PARTY_SIZES` — defaults to `2,3,4,5` (5 = Yelp's "5+").

## Configure the API side (COLLECTOR_TOKEN)

The `/api/collect/<slug>` endpoint is inert until `COLLECTOR_TOKEN` is set.

- **Production (her Cloudflare Worker):**
  ```bash
  npx wrangler secret put COLLECTOR_TOKEN     # paste the same value as .env
  npm run deploy
  ```
- **Local preview:** create `.dev.vars` at the repo root:
  ```
  COLLECTOR_TOKEN=your-shared-secret
  ```
  then `npm run preview` (serves at http://127.0.0.1:8787).

## Run it

```bash
# scrape + print, without posting (safe, but still fetches Yelp):
RWL_DRY_RUN=true ./run.sh
# real run (posts to RWL_API_BASE):
./run.sh
```

## Schedule every 15 minutes (macOS launchd)

```bash
cp com.restowaitlist.collector.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.restowaitlist.collector.plist
# logs: ~/.restowaitlist/collector.log and collector.err.log
# to stop: launchctl unload ~/Library/LaunchAgents/com.restowaitlist.collector.plist
```

Runs at :00/:15/:30/:45. Each cycle warms one Chrome profile, reads the
configured party sizes with human-like pauses, and posts them in one batch.
Readings are bucketed to the 15-minute slot, so the API's uniqueness constraint
makes re-runs idempotent.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `RWL_API_BASE` | `http://127.0.0.1:8787` | API base URL to POST to |
| `RWL_SLUG` | `din-tai-fung-new-york-3` | Restaurant slug |
| `RWL_COLLECTOR_TOKEN` | — | Bearer token; must match the Worker secret |
| `RWL_PARTY_SIZES` | `2,3,4,5` | Party sizes to record each cycle |
| `RWL_WAIT_URL` | Yelp waitlist URL w/ `{size}` | Per-size page template |
| `RWL_WARMUP_URL` | Yelp biz page | Warm-up navigation (set empty to skip) |
| `RWL_PROFILE_DIR` | `~/.restowaitlist/chrome-profile` | Persistent Chrome profile |
| `RWL_HEADLESS` | `false` | Keep false — headless is blocked |
| `RWL_DRY_RUN` | `false` | Scrape and print without posting |
