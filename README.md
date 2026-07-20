# RestoWaitlist

RestoWaitlist records a simple 15-minute wait-time table for Din Tai Fung New York (or another
configured restaurant): one timestamp and one estimate each for parties of 2, 3, 4, 5, and 6.
The database stays on the local Mac. A small static site publishes the table through GitHub Pages.

## Important source boundary

Yelp returned a protected/blocked response to this project’s earlier HTTP check. This project does
not bypass DataDome, solve CAPTCHAs, rotate identities, simulate human behavior, log in, or submit
a waitlist form. It makes no automated Yelp requests in the default configuration.

The supported production path is a **complete manual snapshot** entered by a person, or a separate
data feed for which the operator has clear permission. A snapshot is validated before it is stored:
it must contain every configured party size and each value must be a recognizable displayed wait
estimate (for example, `10-15 mins`, `No wait`, or `Waitlist closed`). Missing values are never
invented.

## What runs where

```text
person / authorized source
          │ writes one complete local snapshot
          ▼
  this Mac: SQLite + 15-minute launchd task
          │ exports static JSON
          ▼
  fork's gh-pages branch → GitHub Pages table
```

The scheduled task never opens a restaurant page. It only reads
`data/inbox/latest-waits.json`, updates the local SQLite database, and publishes changed static
files.

## Local setup

Requirements: Python 3.12+ and GitHub CLI authenticated to the fork.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
cp config.example.toml config.toml
```

`config.toml` is ignored by Git. The example defaults to parties 2–6, a 15-minute interval, and
manual snapshots. It keeps the supplied Yelp page only as source metadata; no command reads it.

Enter a complete reading after viewing values through an allowed route:

```bash
.venv/bin/dtf-waitwatch capture \
  --wait '2=No wait' \
  --wait '3=10-15 mins' \
  --wait '4=20 min' \
  --wait '5=30+ min' \
  --wait '6=Waitlist closed'
```

This writes an atomic snapshot to `data/inbox/latest-waits.json`. You can instead write the same
format from an authorized system:

```json
{
  "schema_version": 1,
  "captured_at": "2026-07-20T18:15:00-04:00",
  "waits": {
    "2": "No wait",
    "3": "10-15 mins",
    "4": "20 min",
    "5": "30+ min",
    "6": "Waitlist closed"
  }
}
```

Ingest that snapshot and generate the local static table:

```bash
.venv/bin/dtf-waitwatch sync-snapshot --config config.toml
python3 -m http.server 8000 --directory site
```

Open `http://localhost:8000`. The site shows the most recent 31 days by default; SQLite retains
the full local history. Use `--days` with `sync-snapshot` or `export-site` to change the published
window, or omit it to publish all history.

## Continuous local operation

Install the macOS user LaunchAgent after the first local sync:

```bash
./scripts/install-launch-agent.sh
```

It runs at 1, 16, 31, and 46 minutes past each hour, allowing a snapshot captured near each
quarter-hour to be put in its correct table slot. Its logs are under `logs/`. It skips a snapshot
older than 30 minutes and does not manufacture a row when no complete fresh snapshot exists.

Useful checks:

```bash
launchctl print gui/$(id -u)/com.restowaitlist.waitwatch
tail -f logs/waitwatch.log
.venv/bin/dtf-waitwatch status --config config.toml
```

## GitHub Pages publishing

The publisher copies `site/` into a separate `gh-pages` branch. Local observations and generated
`site/data/waits.json` stay out of the code branch and the PR.

```bash
./scripts/sync-and-publish.sh
```

On the first run, configure GitHub Pages on the fork to deploy the root of `gh-pages`:

```bash
./scripts/enable-github-pages.sh
```

The script creates or updates the Pages setting. The resulting address is normally
`https://OWNER.github.io/restowaitlist/`. The static table has no server-side collector and no
secrets.

## Validation

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npm ci
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npm run typecheck
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npm run lint
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npm run test:web
```

The repository also retains the original generic Python reporting toolkit and worker-oriented web
experiment. The static `site/` plus local snapshot workflow above is the supported deployment for
this use case.
