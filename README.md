# RestoWaitlist

RestoWaitlist is a hosted restaurant wait dashboard plus the original `dtf-waitwatch` Python
collection toolkit. The web application links to a restaurant's official waitlist, lets its owner
record the displayed wait manually, and turns those readings into history and a confidence-aware
timing recommendation. It does not scrape or join a waitlist automatically.

## Live dashboard (public)

Automated Din Tai Fung wait readings are published on this repo's [`gh-pages`](https://github.com/mirabellebrown/restowaitlist/tree/gh-pages) branch:

| | |
|---|---|
| **Live dashboard** | https://jdelpego.github.io/restowaitlist/ |
| **Raw wait archive** | [`data/waits.json`](https://github.com/mirabellebrown/restowaitlist/blob/gh-pages/data/waits.json) |
| **Site source** | [`gh-pages` branch](https://github.com/mirabellebrown/restowaitlist/tree/gh-pages) |

The archive on `gh-pages` is the source of truth in this repository. The public dashboard URL above
mirrors that branch (GitHub Pages). To serve the dashboard under
`https://mirabellebrown.github.io/restowaitlist/` as well, a repo admin can enable
**Settings → Pages → Deploy from branch `gh-pages` / root**.

The production-shaped web surface uses React/vinext on a Cloudflare Worker-compatible runtime and
D1 for durable restaurant configuration and observation history. Its signed-in management page
supports additional restaurants, party sizes, timezones, source URLs, and conservative collection
intervals.

## Web application

Node.js 22.13 or newer is required. Install and validate with:

```bash
npm ci
npm run typecheck
npm run lint
npm run test:web
npm run build
```

Local development uses the Worker-aware command:

```bash
npm run dev
```

For a production-shaped local preview with durable local D1 data, use `npm run preview`. Its state
lives under `.wrangler/local-preview`, outside generated build output, so rebuilding does not erase
manual observations.

The primary routes are:

- `/` — Din Tai Fung New York dashboard for party size four
- `/restaurants/{slug}` — reusable restaurant dashboard
- `/manage` — ChatGPT-sign-in-gated restaurant configuration
- `/api/health` — database and collector health
- `/api/observations/{slug}` — authenticated manual wait entry

The D1 schema lives in `db/schema.ts`; checked-in migrations live in `drizzle/`. The application
initializes missing tables defensively and seeds the supplied Din Tai Fung configuration. A public
page visit reuses the latest stored reading. Open the official waitlist from the dashboard, enter
the wait shown there, and RestoWaitlist timestamps and saves it. The same form can backfill past
readings by supplying the original date/time and any party size from 1 to 20; leaving the date blank
records the reading at the current time.

### Live source status

The supplied Din Tai Fung Yelp waitlist URL declines automated access. The web application therefore
runs in manual mode and makes no background request to Yelp. Automated collection remains disabled
unless an authorized data source is arranged later.

The twelve confirmed Din Tai Fung readings from July 20, 2026 are seeded idempotently. They remain
available after a clean local rebuild and initialize a fresh deployment without creating duplicates.

### Deploy on Cloudflare Free

The checked-in `wrangler.jsonc` deploys one Worker and automatically provisions the `DB` D1 binding.
From the repository root:

```bash
npm ci
npx wrangler login
npm run deploy
```

Complete Cloudflare's browser authorization when `wrangler login` opens it. The deploy command
prints the public `workers.dev` URL. Verify the deployment at `/api/health`. The application creates
its tables and Din Tai Fung record on first access, so no separate first-deploy migration command is
required.

The direct Cloudflare deployment does not provide OpenAI Sites' `/manage` authentication routes.
The dashboard and Cron Trigger work independently; configure a Cloudflare-native admin login before
exposing management functions there.

## Python collection toolkit

`dtf-waitwatch` records a restaurant's publicly displayed wait estimate on a fixed schedule,
preserves the parsed evidence, produces a standalone report, and recommends a risk-aware time to
join a waitlist. Despite the historical project name, locations and providers are configuration:
the same program can monitor Din Tai Fung, La Parisienne, or another restaurant when the source
permits automated access.

The included real-world example is configured for the user-supplied Din Tai Fung New York Yelp
waitlist URL with `party_size=4`. It is disabled until permission is acknowledged. The project does
not log in, bypass protection, collect customer data, or click any Join/Submit/Confirm control.

## Install

Python 3.12 or newer is required.

With `uv`:

```bash
uv venv
uv pip install -e ".[dev]"
```

With ordinary `pip`:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Playwright is optional and should be used only when the original authorized HTTP response does not
contain the visible wait value:

```bash
python -m pip install -e ".[browser]"
playwright install chromium
```

## First run and authorization

Copy the documented example, then run the wizard. The wizard reuses the copied values as defaults:

```bash
cp config.example.toml config.toml
dtf-waitwatch init
```

On PowerShell, use `Copy-Item config.example.toml config.toml`. Automated sources show their exact
URL and ask you to confirm that you reviewed applicable terms and have permission to poll it. This
local acknowledgment is an audit aid; it does **not** grant permission. If the terms do not permit
automation, select `manual` and keep the fully functional CSV workflow.

The Din Tai Fung example uses:

```text
https://www.yelp.com/waitlist/din-tai-fung-new-york-3?party_size=4
```

The analogous user-supplied La Parisienne example demonstrates restaurant portability:

```text
https://www.yelp.com/waitlist/la-parisienne-new-york-5?party_size=4&utm_medium=waitlist_widget&utm_source=biz_details
```

For another restaurant, replace `location.name`, `location.official_url`,
`location.wait_source_url`, `location.provider`, `location.timezone`, and the CSS `source.selector`.
Keep the party size in `[collection]` consistent with the waitlist URL. Add verified opening hours
if known. No secrets belong in this file.

## Validate and collect

`doctor` validates the timezone and database, performs one permitted read, and prints exactly the
text/value the parser thinks is the wait estimate. It never joins a waitlist:

```bash
dtf-waitwatch doctor
dtf-waitwatch collect-once
dtf-waitwatch run --days 5 --interval-minutes 15
dtf-waitwatch status
```

HTTP is preferred because it makes one ordinary request. If `doctor` reports that the selector did
not match and an authorized inspection confirms the wait value exists only after JavaScript
rendering, install the browser extra, set `source.type = "playwright"`, and configure the exact
visible-value selector. Playwright loads one page and reads one element; it does not click or submit.
HTTP 401/403/429, CAPTCHA, and bot-block responses are terminal for that interval and are not evaded.

Keep the machine awake, powered, and connected for the five-day window. The scheduler uses
`start + n × interval`, so it does not drift. Restarting resumes the persisted run, labels elapsed
slots `missed_due_to_downtime`, and waits for the next scheduled slot instead of polling rapidly.

## Manual CSV mode

Set `source.type = "manual"` and `source.manual_csv_path` as needed. A sample is in
`examples/manual-waits.csv` with these columns:

```text
observed_at_local,party_size,status,wait_min_minutes,wait_max_minutes,raw_wait_text
```

Import a history directly:

```bash
dtf-waitwatch import-csv examples/manual-waits.csv
```

Timestamps without an offset are interpreted in the configured restaurant timezone. Only short
wait text is stored; do not put customer names, phone numbers, email addresses, or notes containing
personal data in the CSV.

## Reports, exports, and recommendations

```bash
dtf-waitwatch export --format csv --output data/waits.csv
dtf-waitwatch report --output reports/wait-report.html
dtf-waitwatch recommend --target "2026-08-01 19:00" --party-size 4 --risk 0.80
dtf-waitwatch recommend --target "next Saturday 19:00" --party-size 4 --format json
```

The algorithm evaluates 15-minute candidates in the prior four hours. It first seeks the same
weekday across at least three dates, then the same weekday/weekend category, then all days at nearby
times. Samples must be within ±60 minutes; closer slots weigh more, and each date is normalized so
adjacent observations do not masquerade as independent days. P50 uses range midpoints. Conservative
percentiles use displayed upper bounds; an open-ended `90+` value necessarily uses its 90-minute
lower bound and emits a warning. The latest candidate whose risk-percentile wait ends by the target
is selected, but never before configured opening.

Record actual outcomes to calibrate the difference between displayed and real waits:

```bash
dtf-waitwatch record-actual \
  --party-size 4 \
  --joined-at "2026-08-01 17:30" \
  --seated-at "2026-08-01 18:52" \
  --displayed-min 70 \
  --displayed-max 90
```

Without those records the program explicitly says that no actual-wait calibration is available. A
capped median adjustment is used after feedback exists; displayed estimates are never claimed to
equal seating waits.

## Fully synthetic demonstration

This contacts no restaurant and labels every value synthetic:

```bash
dtf-waitwatch init-demo --force
dtf-waitwatch run --demo --accelerated
dtf-waitwatch report
dtf-waitwatch recommend --target "next Saturday 19:00" --party-size 2
```

The accelerated run creates five days of deterministic history immediately and an automatic HTML
report. Do not combine the demo database with real observations.

## Docker Compose

After preparing `config.toml`, start the ordinary HTTP/manual/demo image:

```bash
docker compose build waitwatch
docker compose run --rm waitwatch doctor --config /app/config.toml
docker compose up -d waitwatch
docker compose logs -f waitwatch
```

For a permitted browser source:

```bash
docker compose --profile browser build waitwatch-browser
docker compose --profile browser up -d waitwatch-browser
```

Both services persist `./data` and `./reports`; use only one collector service for a location.

## Database backup and restore

Stop the collector (or use SQLite's online backup command), then copy the database and its WAL/SHM
companions if present:

```bash
sqlite3 data/waits.sqlite3 ".backup 'data/waits-backup.sqlite3'"
cp data/waits-backup.sqlite3 data/waits.sqlite3
```

On PowerShell, the safe offline equivalent is `Copy-Item` after `docker compose stop` or after the
local collector exits. Restore into the path named by `[database].path`.

## Troubleshooting

- **Permission refused:** use manual CSV mode unless the provider/source explicitly permits polling.
- **Selector stopped matching:** run `doctor`; update only `source.selector`/`attribute` after an
  authorized inspection. Stored hashes and short fragments help distinguish markup changes.
- **Blocked response:** the app records `source_blocked` and does not retry or evade it.
- **Missing intervals:** `status` and the report distinguish downtime from source and parser errors.
- **Wrong local times:** use an IANA zone such as `America/New_York`, not a fixed abbreviation.
- **Recommendation unavailable:** collect valid open-hour observations near candidate join times.

Five days is enough to exercise the workflow but usually only one observation date per weekday, so
same-weekday confidence will be very low. Multiple weeks add independent dates, improve the fallback
level, expose week-to-week variability, and can raise confidence. Holidays, weather, promotions,
source behavior, and walk-in demand can still make history unrepresentative.

## Development checks

Tests never contact external sites and use only synthetic HTML/data:

```bash
pytest
ruff check .
ruff format --check .
npm run typecheck
npm run lint
npm run test:web
npm run build
```
