from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dtf_waitwatch.config import AppConfig
from dtf_waitwatch.database import Database
from dtf_waitwatch.recommendation import InsufficientDataError, recommend


def generate_report(
    database: Database,
    config: AppConfig,
    location_id: int,
    output: str | Path = "reports/wait-report.html",
) -> Path:
    rows = database.list_observations(location_id)
    if not rows:
        raise ValueError(
            "No observations exist; collect or import data before generating a report."
        )
    frame = pd.DataFrame([dict(row) for row in rows])
    frame["scheduled_at_utc"] = pd.to_datetime(frame["scheduled_at_utc"], utc=True)
    frame["local_time"] = frame["scheduled_at_utc"].dt.tz_convert(config.location.timezone)
    frame["date"] = frame["local_time"].dt.date.astype(str)
    frame["time"] = frame["local_time"].dt.strftime("%H:%M")
    frame["day_category"] = frame["local_time"].dt.weekday.map(
        lambda value: "Weekend" if value >= 5 else "Weekday"
    )
    valid = frame[frame["status"].isin(["wait_available", "no_wait"])].copy()
    run_ids = frame["run_id"].nunique()
    expected = _expected_observations(database, frame)
    completeness = len(frame) / expected if expected else 0
    missed = int((frame["status"] == "missed_due_to_downtime").sum())
    failed_statuses = {"source_blocked", "parse_error", "network_error", "temporarily_unavailable"}
    failed = int(frame["status"].isin(failed_statuses).sum())

    figures: list[str] = []
    if not valid.empty:
        figures.append(_time_series(valid).to_html(full_html=False, include_plotlyjs=True))
        figures.append(
            px.box(
                valid,
                x="date",
                y="wait_midpoint_minutes",
                color="party_size",
                title="Daily comparison",
                labels={"wait_midpoint_minutes": "Displayed wait midpoint (minutes)"},
            ).to_html(full_html=False, include_plotlyjs=False)
        )
        summary = (
            valid.groupby(["time", "party_size"], as_index=False)["wait_midpoint_minutes"]
            .median()
            .rename(columns={"wait_midpoint_minutes": "median_wait"})
        )
        figures.append(
            px.line(
                summary,
                x="time",
                y="median_wait",
                color="party_size",
                title="Time-of-day median",
            ).to_html(full_html=False, include_plotlyjs=False)
        )
        figures.append(
            px.box(
                valid,
                x="day_category",
                y="wait_midpoint_minutes",
                color="party_size",
                title="Weekday versus weekend",
            ).to_html(full_html=False, include_plotlyjs=False)
        )
    status_table = pd.crosstab(frame["time"], frame["status"]).to_html(classes="data-table")
    error_counts = (
        frame[frame["status"].isin(failed_statuses)]["status"]
        .value_counts()
        .rename_axis("status")
        .to_frame("count")
        .to_html(classes="data-table")
    )
    party_counts = (
        frame.groupby("party_size")
        .size()
        .rename("observations")
        .to_frame()
        .to_html(classes="data-table")
    )
    recommendations = _example_recommendations(database, config, location_id, valid)
    synthetic_notice = (
        "<p class='warning'><strong>SYNTHETIC DEMO DATA:</strong> These values are not real "
        "restaurant observations.</p>"
        if (frame["source_provider"] == "synthetic-demo").any()
        else ""
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Wait report — {config.location.name}</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:1200px;margin:auto;padding:2rem;color:#202124}}
h1,h2{{color:#183153}} .cards{{display:flex;gap:1rem;flex-wrap:wrap}}
.card{{background:#f3f6fa;padding:1rem 1.4rem;border-radius:.5rem;min-width:150px}}
.warning{{border-left:5px solid #c2410c;background:#fff7ed;padding:1rem}}
.data-table{{border-collapse:collapse;max-width:100%;overflow:auto;display:block}}
.data-table th,.data-table td{{border:1px solid #ddd;padding:.35rem .6rem;text-align:right}}
</style></head><body>
<h1>Restaurant wait report</h1>
<p><strong>{config.location.name}</strong> · {config.location.timezone}</p>
{synthetic_notice}
<div class="cards"><div class="card"><strong>{completeness:.1%}</strong><br>completeness</div>
<div class="card"><strong>{len(frame)}</strong><br>recorded rows</div>
<div class="card"><strong>{missed}</strong><br>missed intervals</div>
<div class="card"><strong>{failed}</strong><br>source/parser failures</div>
<div class="card"><strong>{run_ids}</strong><br>collection runs</div></div>
<h2>Wait estimates over time</h2>{"".join(figures)}
<h2>Waitlist open/closed and status by time</h2>{status_table}
<h2>Parser and source errors</h2>{error_counts}
<h2>Samples by party size</h2>{party_counts}
<h2>Example recommendations</h2>{recommendations}
<h2>Interpretation and limitations</h2>
<p>Displayed estimates are provider-supplied estimates, not actual seating waits. The app only
calibrates that difference after actual outcomes are recorded. Ranges use their midpoint for P50
and their upper bound for conservative percentiles. Missing intervals remain missing.</p>
<p class="warning">Five days usually cannot provide a strong same-weekday estimate. Continue
collecting for multiple weeks to improve independent-date coverage and confidence.</p>
</body></html>"""
    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = (config.config_path.parent / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _time_series(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for party_size, group in frame.groupby("party_size"):
        figure.add_trace(
            go.Scatter(
                x=group["local_time"],
                y=group["wait_max_minutes"],
                line={"width": 0},
                showlegend=False,
                hoverinfo="skip",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=group["local_time"],
                y=group["wait_min_minutes"],
                fill="tonexty",
                fillcolor="rgba(40,110,180,.15)",
                line={"width": 0},
                name=f"Party {party_size} range",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=group["local_time"],
                y=group["wait_midpoint_minutes"],
                mode="lines",
                name=f"Party {party_size} midpoint",
            )
        )
    figure.update_layout(title="Displayed wait over time", yaxis_title="Minutes")
    return figure


def _expected_observations(database: Database, frame: pd.DataFrame) -> int:
    run_ids = [int(value) for value in frame["run_id"].unique()]
    total = 0
    with database.connect() as connection:
        for run_id in run_ids:
            run = connection.execute(
                "SELECT * FROM collection_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                continue
            start = datetime.fromisoformat(run["started_at_utc"])
            end = datetime.fromisoformat(run["scheduled_end_at_utc"])
            intervals = max(0, int((end - start).total_seconds() // (run["interval_minutes"] * 60)))
            parties = int(frame.loc[frame["run_id"] == run_id, "party_size"].nunique())
            total += intervals * parties
    return total


def _example_recommendations(
    database: Database, config: AppConfig, location_id: int, valid: pd.DataFrame
) -> str:
    if valid.empty:
        return "<p>No valid observations are available.</p>"
    base = valid["local_time"].max().to_pydatetime() + timedelta(days=1)
    rows: list[dict[str, object]] = []
    for target_hour in (18, 19, 20):
        target = base.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        try:
            result = recommend(
                database=database,
                config=config,
                location_id=location_id,
                target_local=target,
                party_size=config.collection.party_sizes[0],
                risk=config.recommendation.default_risk_percentile,
            )
            rows.append(
                {
                    "target": target.strftime("%a %H:%M"),
                    "recommended_join": result.recommended_join_local.strftime("%H:%M"),
                    "p80_minutes": round(result.p80_minutes),
                    "confidence": result.confidence,
                    "warning": "; ".join(result.warnings),
                }
            )
        except InsufficientDataError as exc:
            rows.append({"target": target.strftime("%a %H:%M"), "warning": str(exc)})
    return pd.DataFrame(rows).to_html(index=False, classes="data-table")
