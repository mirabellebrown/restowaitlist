from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer

from dtf_waitwatch.config import AppConfig, ConfigError, load_config
from dtf_waitwatch.database import Database
from dtf_waitwatch.logging_config import configure_logging
from dtf_waitwatch.models import SourceType
from dtf_waitwatch.publishing import (
    export_site_payload,
    ingest_snapshot,
    load_snapshot,
    parse_snapshot_timestamp,
    write_snapshot,
)
from dtf_waitwatch.recommendation import (
    InsufficientDataError,
    parse_target,
)
from dtf_waitwatch.recommendation import (
    recommend as calculate_recommendation,
)
from dtf_waitwatch.reporting import generate_report
from dtf_waitwatch.scheduler import collect_slot, run_collection
from dtf_waitwatch.sources import PermissionRequiredError, build_source
from dtf_waitwatch.sources.manual_csv import read_manual_csv

app = typer.Typer(
    no_args_is_help=True,
    help="Collect and analyze public restaurant wait estimates with explicit permission controls.",
)
ConfigOption = Annotated[Path, typer.Option("--config", "-c", help="TOML configuration path")]


def _context(config_path: Path) -> tuple[AppConfig, Database, int]:
    config = load_config(config_path)
    database = Database(config.database_path)
    database.initialize()
    location_id = database.ensure_location(config)
    return config, database, location_id


@app.command("init")
def initialize(
    config_path: ConfigOption = Path("config.toml"),
    force: Annotated[bool, typer.Option(help="Replace an existing configuration")] = False,
) -> None:
    """Run the interactive, permission-aware first-run setup wizard."""
    existing: AppConfig | None = None
    if config_path.exists() and not force:
        try:
            existing = load_config(config_path)
            typer.echo(f"Using values from existing configuration: {config_path.resolve()}")
        except ConfigError:
            if not typer.confirm(f"{config_path} is invalid. Replace it?", default=False):
                raise typer.Abort() from None
    location_name = typer.prompt(
        "Location display name",
        default=existing.location.name if existing else "My restaurant",
    )
    address = typer.prompt(
        "Street address (optional)",
        default=(existing.location.address if existing and existing.location.address else ""),
        show_default=False,
    )
    official_url = typer.prompt(
        "Official or public restaurant-page URL",
        default=existing.location.official_url if existing else "",
        show_default=False,
    )
    wait_url = typer.prompt(
        "Authorized wait-data source URL",
        default=existing.location.wait_source_url if existing else "",
        show_default=False,
    )
    source_type = typer.prompt(
        "Source type (http, playwright, manual, demo)",
        default=existing.source.type.value if existing else "manual",
    ).lower()
    try:
        parsed_source_type = SourceType(source_type)
    except ValueError as exc:
        raise typer.BadParameter("source type must be http, playwright, manual, or demo") from exc
    timezone_name = typer.prompt(
        "IANA timezone",
        default=existing.location.timezone if existing else "America/New_York",
    )
    default_parties = (
        ",".join(str(size) for size in existing.collection.party_sizes) if existing else "2"
    )
    party_sizes = [
        int(value.strip())
        for value in typer.prompt("Party sizes", default=default_parties).split(",")
    ]
    duration_days = typer.prompt(
        "Collection duration in days",
        default=existing.collection.duration_days if existing else 5.0,
        type=float,
    )
    interval_minutes = typer.prompt(
        "Collection interval in minutes",
        default=existing.collection.interval_minutes if existing else 15,
        type=int,
    )
    risk = typer.prompt(
        "Default recommendation risk percentile",
        default=existing.recommendation.default_risk_percentile if existing else 0.80,
        type=float,
    )
    database_path = typer.prompt(
        "SQLite database path",
        default=existing.database.path if existing else "./data/waits.sqlite3",
    )
    existing_hours = _format_opening_hours(existing.opening_hours) if existing else ""
    hours_text = typer.prompt(
        "Weekly hours (optional: monday=11:00-22:00; saturday=11:00-23:00)",
        default=existing_hours,
        show_default=bool(existing_hours),
    )
    opening_hours = _parse_opening_hours(hours_text)
    selector = (
        typer.prompt(
            "CSS selector containing only the visible current wait estimate",
            default=existing.source.selector if existing else "[data-wait-estimate]",
        )
        if parsed_source_type in {SourceType.HTTP, SourceType.PLAYWRIGHT}
        else "[data-wait-estimate]"
    )
    acknowledged = False
    reviewed_at: str | None = None
    if parsed_source_type in {SourceType.HTTP, SourceType.PLAYWRIGHT}:
        typer.echo(f"\nSource URL: {wait_url}")
        typer.echo(
            "Automated access must be allowed by the source and applicable terms. This program "
            "will not log in, bypass controls, or join a waitlist. Your acknowledgment records "
            "your review; it does not create permission."
        )
        acknowledged = typer.confirm(
            "Have you reviewed the source terms and confirmed you have permission to poll it?",
            default=False,
        )
        reviewed_at = datetime.now(UTC).isoformat() if acknowledged else None
    config_text = _render_config(
        name=location_name,
        address=address,
        timezone_name=timezone_name,
        official_url=official_url,
        wait_url=wait_url,
        provider=existing.location.provider if existing else "generic",
        source_type=parsed_source_type.value,
        selector=selector,
        permission_acknowledged=acknowledged,
        permission_reviewed_at=reviewed_at,
        party_sizes=party_sizes,
        duration_days=duration_days,
        interval_minutes=interval_minutes,
        risk=risk,
        database_path=database_path,
        manual_csv_path=(
            existing.source.manual_csv_path if existing else "./data/manual-waits.csv"
        ),
        manual_snapshot_path=(
            existing.source.manual_snapshot_path
            if existing
            else "./data/inbox/latest-waits.json"
        ),
        opening_hours=opening_hours,
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")
    # Reload before touching the database so invalid input cannot leave a half-configured DB.
    config = load_config(config_path)
    database = Database(config.database_path)
    database.initialize()
    database.ensure_location(config)
    typer.echo(f"Configuration written to {config_path.resolve()}")


@app.command("init-demo")
def init_demo(
    config_path: ConfigOption = Path("config.toml"),
    force: Annotated[bool, typer.Option(help="Replace an existing configuration")] = False,
) -> None:
    """Create a fully local profile for clearly labeled synthetic data."""
    if config_path.exists() and not force:
        raise typer.BadParameter(f"{config_path} already exists; use --force to replace it")
    hours = {
        day: ["11:00-23:00"]
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _render_config(
            name="Synthetic Demo Restaurant",
            address="",
            timezone_name="America/New_York",
            official_url="https://example.invalid/demo-restaurant",
            wait_url="demo://synthetic-wait-estimates",
            provider="synthetic-demo",
            source_type="demo",
            selector="[data-wait-estimate]",
            permission_acknowledged=False,
            permission_reviewed_at=None,
            party_sizes=[2],
            duration_days=5,
            interval_minutes=15,
            risk=0.80,
            database_path="./data/demo-waits.sqlite3",
            manual_csv_path="./data/manual-waits.csv",
            manual_snapshot_path="./data/inbox/latest-waits.json",
            opening_hours=hours,
        ),
        encoding="utf-8",
    )
    config, database, _ = _context(config_path)
    typer.echo(f"Synthetic demo initialized at {config.config_path}")
    typer.echo(f"Synthetic database: {database.path}")


@app.command()
def doctor(config_path: ConfigOption = Path("config.toml")) -> None:
    """Validate config, storage, access, and the configured wait parser."""
    try:
        config, database, _ = _context(config_path)
        typer.echo(f"Configuration: valid ({config.config_path})")
        typer.echo(f"Timezone: valid ({config.location.timezone})")
        with database.connect() as connection:
            connection.execute("CREATE TEMP TABLE writable_check(value INTEGER)")
        typer.echo(f"Database: writable ({database.path})")
        typer.echo(f"Source URL: {config.location.wait_source_url}")
        source = build_source(config)
        results = source.collect(config.collection.party_sizes, datetime.now(UTC))
        for party_size, observation in results.items():
            parsed = observation.parsed
            typer.echo(
                f"Party {party_size}: status={parsed.status.value} "
                f"text={parsed.raw_wait_text!r} min={parsed.wait_min_minutes} "
                f"max={parsed.wait_max_minutes}"
            )
            if parsed.error_message:
                typer.echo(f"Parser/source detail: {parsed.error_message}")
        failed_statuses = {
            "network_error",
            "parse_error",
            "source_blocked",
            "temporarily_unavailable",
        }
        if any(result.parsed.status.value in failed_statuses for result in results.values()):
            raise typer.Exit(1)
    except (ConfigError, PermissionRequiredError, OSError, sqlite3.Error, ValueError) as exc:
        typer.echo(f"Doctor failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("collect-once")
def collect_once(config_path: ConfigOption = Path("config.toml")) -> None:
    """Record exactly one scheduled observation without joining any waitlist."""
    try:
        config, database, location_id = _context(config_path)
        source = build_source(config)
        now = datetime.now(UTC)
        run_id = database.create_run(
            location_id,
            now,
            now + timedelta(minutes=config.collection.interval_minutes),
            config.collection.interval_minutes,
            config.source.type.value,
        )
        results = collect_slot(
            config=config,
            database=database,
            source=source,
            run_id=run_id,
            location_id=location_id,
            scheduled_at=now,
        )
        database.finish_run(run_id)
        if results is None:
            typer.echo("Recorded restaurant_closed (outside configured opening hours).")
        else:
            for party_size, observation in results.items():
                parsed = observation.parsed
                typer.echo(
                    f"Party {party_size}: {parsed.status.value}; {parsed.raw_wait_text!r}; "
                    f"range={parsed.wait_min_minutes}-{parsed.wait_max_minutes} minutes"
                )
    except (ConfigError, PermissionRequiredError, ValueError, OSError) as exc:
        typer.echo(f"Collection failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("run")
def run_command(
    config_path: ConfigOption = Path("config.toml"),
    days: Annotated[float | None, typer.Option(help="Override configured duration in days")] = None,
    interval_minutes: Annotated[
        int | None, typer.Option(help="Override configured interval")
    ] = None,
    demo: Annotated[bool, typer.Option(help="Force the synthetic source")] = False,
    accelerated: Annotated[
        bool, typer.Option(help="Generate a demo history immediately without sleeping")
    ] = False,
    verbose: Annotated[bool, typer.Option(help="Enable debug logging")] = False,
) -> None:
    """Start or safely resume a scheduled collection run."""
    configure_logging(verbose)
    try:
        config, database, location_id = _context(config_path)
        if demo:
            config.source.type = SourceType.DEMO
            config.location.provider = "synthetic-demo"
            config.location.wait_source_url = "demo://synthetic-wait-estimates"
            location_id = database.ensure_location(config)
        if accelerated and config.source.type is not SourceType.DEMO:
            raise ValueError("--accelerated is available only with --demo or a demo configuration")
        source = build_source(config)
        report_path = (config.config_path.parent / "reports" / "wait-report.html").resolve()

        def finish_report() -> None:
            generate_report(database, config, location_id, report_path)

        run_id = run_collection(
            config=config,
            database=database,
            source=source,
            days=days,
            interval_minutes=interval_minutes,
            accelerated=accelerated,
            create_report=finish_report,
        )
        typer.echo(f"Run {run_id} stopped or completed safely.")
        if database.latest_run(location_id)["state"] == "completed":
            typer.echo(f"Report: {report_path}")
    except (ConfigError, PermissionRequiredError, ValueError, OSError) as exc:
        typer.echo(f"Run failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def status(config_path: ConfigOption = Path("config.toml")) -> None:
    """Show the latest run and observation status counts."""
    config, database, location_id = _context(config_path)
    run = database.latest_run(location_id)
    if run is None:
        typer.echo("No collection runs exist.")
        return
    typer.echo(
        f"Run {run['id']}: {run['state']} | {run['started_at_utc']} to "
        f"{run['scheduled_end_at_utc']} | interval {run['interval_minutes']} minutes"
    )
    with database.connect() as connection:
        counts = connection.execute(
            "SELECT status, COUNT(*) count FROM observations WHERE run_id=? GROUP BY status",
            (run["id"],),
        ).fetchall()
    for row in counts:
        typer.echo(f"  {row['status']}: {row['count']}")
    typer.echo(f"Database: {database.path}")
    typer.echo(f"Location: {config.location.name}")


@app.command("record-actual")
def record_actual(
    party_size: Annotated[int, typer.Option(help="Seated party size")],
    joined_at: Annotated[str, typer.Option(help="Local ISO date/time or ISO time with offset")],
    seated_at: Annotated[str, typer.Option(help="Local ISO date/time or ISO time with offset")],
    displayed_min: Annotated[int | None, typer.Option(help="Displayed lower wait bound")] = None,
    displayed_max: Annotated[int | None, typer.Option(help="Displayed upper wait bound")] = None,
    notes: Annotated[str, typer.Option(help="Optional non-personal notes")] = "",
    config_path: ConfigOption = Path("config.toml"),
) -> None:
    """Record an actual seating outcome for robust estimate calibration."""
    config, database, location_id = _context(config_path)
    joined = parse_target(joined_at, config.timezone)
    seated = parse_target(seated_at, config.timezone)
    row_id = database.record_actual(
        location_id=location_id,
        party_size=party_size,
        joined_at=joined,
        seated_at=seated,
        displayed_min=displayed_min,
        displayed_max=displayed_max,
        notes=notes,
    )
    typer.echo(
        f"Recorded actual wait #{row_id}: {(seated - joined).total_seconds() / 60:.0f} minutes"
    )


@app.command("recommend")
def recommend_command(
    target: Annotated[str, typer.Option(help="Local ISO target or 'next Saturday 19:00'")],
    party_size: Annotated[int, typer.Option(help="Requested party size")],
    risk: Annotated[float | None, typer.Option(help="Risk percentile, e.g. 0.80")] = None,
    output_format: Annotated[str, typer.Option("--format", help="text or json")] = "text",
    config_path: ConfigOption = Path("config.toml"),
) -> None:
    """Recommend the latest risk-aware waitlist join time."""
    try:
        config, database, location_id = _context(config_path)
        target_local = parse_target(target, config.timezone)
        chosen_risk = risk if risk is not None else config.recommendation.default_risk_percentile
        result = calculate_recommendation(
            database=database,
            config=config,
            location_id=location_id,
            target_local=target_local,
            party_size=party_size,
            risk=chosen_risk,
        )
        if output_format == "json":
            typer.echo(json.dumps(result.to_dict(), indent=2))
        elif output_format == "text":
            _print_recommendation(result)
        else:
            raise typer.BadParameter("--format must be text or json")
    except (ConfigError, InsufficientDataError, ValueError) as exc:
        typer.echo(f"Recommendation failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("export")
def export_command(
    output: Annotated[Path, typer.Option(help="Destination CSV path")],
    output_format: Annotated[str, typer.Option("--format", help="Currently: csv")] = "csv",
    config_path: ConfigOption = Path("config.toml"),
) -> None:
    """Export raw observations without fabricating missing values."""
    if output_format != "csv":
        raise typer.BadParameter("Only CSV export is currently supported")
    config, database, location_id = _context(config_path)
    output_path = output if output.is_absolute() else config.config_path.parent / output
    count = database.export_csv(output_path, location_id)
    typer.echo(f"Exported {count} observations to {output_path.resolve()}")


@app.command("report")
def report_command(
    output: Annotated[Path, typer.Option(help="Standalone HTML path")] = Path(
        "reports/wait-report.html"
    ),
    config_path: ConfigOption = Path("config.toml"),
) -> None:
    """Build a standalone HTML analysis report."""
    config, database, location_id = _context(config_path)
    try:
        path = generate_report(database, config, location_id, output)
        typer.echo(f"Report written to {path}")
    except ValueError as exc:
        typer.echo(f"Report failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("import-csv")
def import_csv(
    input_path: Annotated[Path, typer.Argument(help="Manual CSV input")],
    config_path: ConfigOption = Path("config.toml"),
) -> None:
    """Import manually recorded observations into the configured database."""
    config, database, location_id = _context(config_path)
    rows = read_manual_csv(input_path, config.timezone)
    if not rows:
        typer.echo("No CSV rows to import.")
        return
    observed_times = [row["observed_at"] for row in rows]
    start = min(observed_times)
    end = max(observed_times) + timedelta(minutes=config.collection.interval_minutes)
    run_id = database.create_run(
        location_id,
        start,
        end,
        config.collection.interval_minutes,
        "manual",
    )
    inserted = 0
    from dtf_waitwatch.models import ParsedWait, SourceObservation

    for row in rows:
        observed = row["observed_at"]
        parsed = row["parsed"]
        assert isinstance(observed, datetime)
        assert isinstance(parsed, ParsedWait)
        inserted += int(
            database.insert_observation(
                run_id=run_id,
                location_id=location_id,
                party_size=int(row["party_size"]),
                scheduled_at=observed,
                local_timezone=config.timezone,
                observation=SourceObservation(
                    parsed=parsed,
                    source_url=str(input_path.resolve()),
                    source_provider="manual-csv",
                    observed_at_utc=observed.astimezone(UTC),
                ),
            )
        )
    database.finish_run(run_id)
    typer.echo(f"Imported {inserted} manual observations into run {run_id}.")


@app.command("capture")
def capture_snapshot(
    wait: Annotated[
        list[str] | None,
        typer.Option("--wait", help="Party size and visible wait text, e.g. 2=10-15 mins"),
    ] = None,
    captured_at: Annotated[
        str | None,
        typer.Option(help="Optional local ISO timestamp; defaults to the current time"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(help="Snapshot path; defaults to source.manual_snapshot_path"),
    ] = None,
    config_path: ConfigOption = Path("config.toml"),
) -> None:
    """Write one complete manual party-size snapshot for the local sync job.

    This command accepts values copied or entered by a person.  It intentionally
    does not open, automate, or submit any third-party waitlist page.
    """

    try:
        config, _, _ = _context(config_path)
        waits: dict[int, str] = {}
        for item in wait or []:
            try:
                party_text, raw_wait = item.split("=", maxsplit=1)
                party_size = int(party_text.strip())
            except ValueError as exc:
                raise typer.BadParameter("Each --wait must look like 2=10-15 mins") from exc
            if not raw_wait.strip():
                raise typer.BadParameter(f"Party size {party_size} has an empty wait value")
            if party_size in waits:
                raise typer.BadParameter(f"Party size {party_size} was supplied more than once")
            waits[party_size] = raw_wait.strip()
        timestamp = (
            parse_snapshot_timestamp(captured_at, config.timezone)
            if captured_at
            else datetime.now(UTC)
        )
        destination = output or config.manual_snapshot_path
        if not destination.is_absolute():
            destination = config.config_path.parent / destination
        path = write_snapshot(destination, captured_at_utc=timestamp, waits=waits, config=config)
        typer.echo(f"Manual snapshot written to {path.resolve()}")
    except (ConfigError, ValueError, OSError) as exc:
        typer.echo(f"Capture failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("sync-snapshot")
def sync_snapshot(
    input_path: Annotated[
        Path | None,
        typer.Option("--input", help="Snapshot JSON; defaults to source.manual_snapshot_path"),
    ] = None,
    output: Annotated[
        Path,
        typer.Option(help="Static site JSON output path"),
    ] = Path("site/data/waits.json"),
    days: Annotated[
        int | None,
        typer.Option(help="Published history window in days; omit to publish all history"),
    ] = 31,
    max_age_minutes: Annotated[
        float | None,
        typer.Option(help="Skip an older snapshot instead of treating it as current"),
    ] = None,
    config_path: ConfigOption = Path("config.toml"),
) -> None:
    """Ingest one complete local snapshot and regenerate the static table data."""

    try:
        config, database, location_id = _context(config_path)
        source_path = input_path or config.manual_snapshot_path
        if not source_path.is_absolute():
            source_path = config.config_path.parent / source_path
        if source_path.exists():
            snapshot = load_snapshot(source_path, config)
            result = ingest_snapshot(
                database=database,
                config=config,
                location_id=location_id,
                snapshot=snapshot,
                max_age_minutes=max_age_minutes,
            )
            slot = result.scheduled_at_utc.astimezone(config.timezone).isoformat()
            if result.skipped_reason:
                typer.echo(f"Snapshot skipped for {slot}: {result.skipped_reason}.")
            else:
                typer.echo(f"Recorded {result.inserted} observations for {slot}.")
        else:
            typer.echo(f"No snapshot found at {source_path}; preserving existing observations.")
        destination = output if output.is_absolute() else config.config_path.parent / output
        payload = export_site_payload(
            destination,
            database=database,
            config=config,
            location_id=location_id,
            days=days,
        )
        typer.echo(
            f"Published data export: {len(payload['rows'])} table rows -> {destination.resolve()}"
        )
    except (ConfigError, ValueError, OSError) as exc:
        typer.echo(f"Snapshot sync failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("export-site")
def export_site(
    output: Annotated[
        Path,
        typer.Option(help="Static site JSON output path"),
    ] = Path("site/data/waits.json"),
    days: Annotated[
        int | None,
        typer.Option(help="Published history window in days; omit to publish all history"),
    ] = 31,
    config_path: ConfigOption = Path("config.toml"),
) -> None:
    """Export the local database as the simple GitHub Pages table data file."""

    try:
        config, database, location_id = _context(config_path)
        destination = output if output.is_absolute() else config.config_path.parent / output
        payload = export_site_payload(
            destination,
            database=database,
            config=config,
            location_id=location_id,
            days=days,
        )
        typer.echo(
            f"Published data export: {len(payload['rows'])} table rows -> {destination.resolve()}"
        )
    except (ConfigError, ValueError, OSError) as exc:
        typer.echo(f"Site export failed: {exc}", err=True)
        raise typer.Exit(1) from exc


def _print_recommendation(result: object) -> None:
    from dtf_waitwatch.models import Recommendation

    assert isinstance(result, Recommendation)
    target = result.target_local
    target_label = f"{target.strftime('%A, %b')} {target.day} at {_format_time(target)}"
    typer.echo(f"Target table time: {target_label}")
    typer.echo(
        f"Recommended join time at {result.risk:.0%} risk level: "
        f"{_format_time(result.recommended_join_local)}"
    )
    typer.echo("Estimated displayed wait:")
    typer.echo(f"  P50: {result.p50_minutes:.0f} minutes")
    typer.echo(f"  P80: {result.p80_minutes:.0f} minutes")
    typer.echo(f"  P90: {result.p90_minutes:.0f} minutes")
    typer.echo(
        "Expected table-ready window: "
        f"{_format_time(result.expected_ready_start_local)}-"
        f"{_format_time(result.expected_ready_end_local)}"
    )
    typer.echo(
        f"Comparable observations: {result.observation_count} observations across "
        f"{result.independent_dates} independent dates ({result.fallback_level})"
    )
    typer.echo(f"Data range: {result.data_start} to {result.data_end}")
    typer.echo(f"Confidence: {result.confidence}")
    if result.calibration_minutes is None:
        typer.echo("Calibration: no actual seating feedback available")
    else:
        typer.echo(f"Calibration: {result.calibration_minutes:+.0f} minutes (capped robust median)")
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}")


def _format_time(value: datetime) -> str:
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"


def _toml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _format_opening_hours(hours: dict[str, list[str]]) -> str:
    return "; ".join(f"{day}={','.join(periods)}" for day, periods in hours.items())


def _parse_opening_hours(value: str) -> dict[str, list[str]]:
    if not value.strip():
        return {}
    result: dict[str, list[str]] = {}
    try:
        for item in value.split(";"):
            day, periods_text = item.strip().split("=", maxsplit=1)
            periods = [period.strip() for period in periods_text.split(",") if period.strip()]
            if not periods:
                raise ValueError(f"no periods for {day}")
            result[day.strip().lower()] = periods
    except ValueError as exc:
        raise typer.BadParameter(
            "weekly hours must look like 'monday=11:00-22:00; saturday=11:00-23:00'"
        ) from exc
    return result


def _render_config(
    *,
    name: str,
    address: str,
    timezone_name: str,
    official_url: str,
    wait_url: str,
    provider: str,
    source_type: str,
    selector: str,
    permission_acknowledged: bool,
    permission_reviewed_at: str | None,
    party_sizes: list[int],
    duration_days: float,
    interval_minutes: int,
    risk: float,
    database_path: str,
    manual_csv_path: str,
    manual_snapshot_path: str,
    opening_hours: dict[str, list[str]],
) -> str:
    reviewed = _toml_quote(permission_reviewed_at or "")
    parties = ", ".join(str(value) for value in party_sizes)
    lines = [
        "# A permission acknowledgment records your review; it does not create permission.",
        "[location]",
        f"name = {_toml_quote(name)}",
        f"address = {_toml_quote(address)}",
        f"timezone = {_toml_quote(timezone_name)}",
        f"official_url = {_toml_quote(official_url)}",
        f"wait_source_url = {_toml_quote(wait_url)}",
        f"provider = {_toml_quote(provider)}",
        "",
        "[source]",
        f"type = {_toml_quote(source_type)}",
        f"permission_acknowledged = {str(permission_acknowledged).lower()}",
        f"permission_reviewed_at = {reviewed}",
        f"selector = {_toml_quote(selector)}",
        'attribute = ""',
        f"manual_csv_path = {_toml_quote(manual_csv_path)}",
        f"manual_snapshot_path = {_toml_quote(manual_snapshot_path)}",
        "timeout_seconds = 20.0",
        "transient_retry_delay_seconds = 1.0",
        'user_agent = "dtf-waitwatch/0.1 (permission-aware personal monitoring)"',
        "",
        "[collection]",
        f"party_sizes = [{parties}]",
        f"duration_days = {float(duration_days)}",
        f"interval_minutes = {interval_minutes}",
        "",
        "[recommendation]",
        f"default_risk_percentile = {float(risk)}",
        "",
        "[database]",
        f"path = {_toml_quote(database_path)}",
        "",
        "[opening_hours]",
    ]
    for day, periods in opening_hours.items():
        values = ", ".join(_toml_quote(value) for value in periods)
        lines.append(f"{day} = [{values}]")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    app()
