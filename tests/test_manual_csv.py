from pathlib import Path

from typer.testing import CliRunner

from dtf_waitwatch.cli import app
from dtf_waitwatch.models import ObservationStatus
from dtf_waitwatch.sources.manual_csv import read_manual_csv


def test_manual_csv_read(app_config, tmp_path):
    path = tmp_path / "manual.csv"
    path.write_text(
        "observed_at_local,party_size,status,wait_min_minutes,wait_max_minutes,raw_wait_text\n"
        "2026-08-01 17:30,2,wait_available,70,90,70-90 mins\n",
        encoding="utf-8",
    )
    rows = read_manual_csv(path, app_config.timezone)
    assert len(rows) == 1
    assert rows[0]["party_size"] == 2
    assert rows[0]["parsed"].status is ObservationStatus.WAIT_AVAILABLE
    assert rows[0]["observed_at"].utcoffset().total_seconds() == -4 * 3600


def test_manual_csv_import_command(tmp_path: Path):
    config = tmp_path / "config.toml"
    database = tmp_path / "manual.sqlite3"
    config.write_text(
        f"""[location]
name = "Manual Test"
timezone = "America/New_York"
official_url = "https://example.test"
wait_source_url = "manual://csv"
provider = "manual"
[source]
type = "manual"
manual_csv_path = "./manual.csv"
[collection]
party_sizes = [2]
duration_days = 5
interval_minutes = 15
[recommendation]
default_risk_percentile = 0.8
[database]
path = "{database.as_posix()}"
[opening_hours]
""",
        encoding="utf-8",
    )
    csv_path = tmp_path / "import.csv"
    csv_path.write_text(
        "observed_at_local,party_size,status,wait_min_minutes,wait_max_minutes,raw_wait_text\n"
        "2026-08-01 17:30,2,wait_available,70,90,70-90 mins\n"
        "2026-08-01 17:45,2,no_wait,0,0,No wait\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["import-csv", str(csv_path), "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert "Imported 2" in result.output
