"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { summarizeRecommendation } from "@/lib/recommendation";
import type { Observation, RestaurantDashboard } from "@/lib/types";

const statusCopy: Record<Observation["status"], string> = {
  wait_available: "Live estimate",
  no_wait: "No wait shown",
  waitlist_closed: "Waitlist closed",
  restaurant_closed: "Restaurant closed",
  temporarily_unavailable: "Temporarily unavailable",
  source_blocked: "Source blocked",
  parse_error: "Needs source review",
  network_error: "Network unavailable",
  manual: "Manual reading",
};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
  }).format(new Date(value));
}

function currentWait(observation: Observation | undefined): string {
  if (!observation) return "—";
  if (observation.status === "no_wait") return "0 min";
  if (observation.waitMinMinutes === null) return "—";
  if (
    observation.waitMaxMinutes !== null &&
    observation.waitMaxMinutes !== observation.waitMinMinutes
  ) {
    return `${observation.waitMinMinutes}–${observation.waitMaxMinutes} min`;
  }
  return `${observation.waitMinMinutes} min`;
}

function HistoryChart({ observations }: { observations: Observation[] }) {
  const usable = observations
    .filter((item) => item.waitMidpointMinutes !== null)
    .slice(-24);
  if (usable.length < 2) {
    return (
      <div className="empty-chart">
        <div className="empty-line" />
        <p>Wait history will appear after two usable readings.</p>
      </div>
    );
  }

  const max = Math.max(...usable.map((item) => item.waitMidpointMinutes ?? 0), 15);
  const points = usable
    .map((item, index) => {
      const x = (index / (usable.length - 1)) * 100;
      const y = 92 - ((item.waitMidpointMinutes ?? 0) / max) * 76;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="history-chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Recent wait history">
        <polyline className="chart-fill" points={`0,100 ${points} 100,100`} />
        <polyline className="chart-line" points={points} />
      </svg>
      <div className="chart-labels"><span>{formatTime(usable[0].observedAt)}</span><span>{formatTime(usable.at(-1)!.observedAt)}</span></div>
    </div>
  );
}

export function Dashboard({ data }: { data: RestaurantDashboard }) {
  const [partySize, setPartySize] = useState(data.restaurant.partySizes[0] ?? 4);
  const [entryStatus, setEntryStatus] = useState("wait_available");
  const [waitMin, setWaitMin] = useState("");
  const [waitMax, setWaitMax] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "loading" | "done">("idle");
  const [saveError, setSaveError] = useState("");
  const observations = useMemo(
    () => data.observations.filter((item) => item.partySize === partySize),
    [data.observations, partySize],
  );
  const recommendation = useMemo(
    () => summarizeRecommendation(observations),
    [observations],
  );
  const latest = observations.at(-1);

  async function saveManualReading(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaveState("loading");
    setSaveError("");
    try {
      const response = await fetch(`/api/observations/${data.restaurant.slug}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          partySize,
          status: entryStatus,
          waitMinMinutes: waitMin,
          waitMaxMinutes: waitMax,
        }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "The reading could not be saved");
      setSaveState("done");
      window.setTimeout(() => window.location.reload(), 350);
    } catch (error) {
      setSaveState("idle");
      setSaveError(error instanceof Error ? error.message : "The reading could not be saved");
    }
  }

  return (
    <main className="site-shell">
      <nav className="nav-wrap" aria-label="Primary navigation">
        <Link className="wordmark" href="/">RESTO<span>WAIT</span>LIST</Link>
        <div className="nav-links">
          <a href="#history">History</a>
          <Link href="/manage">Manage</Link>
          <span className={`live-dot ${latest ? "is-live" : ""}`} aria-hidden="true" />
          NYC
        </div>
      </nav>

      <section className="hero dashboard-hero">
        <div className="hero-copy">
          <p className="eyebrow">{data.restaurant.city} · PARTY OF {partySize}</p>
          <h1>Time the table.<br />Skip the guesswork.</h1>
          <p className="lede">Check the official waitlist, save what you see, and turn each reading into a calmer dinner plan.</p>
          <div className="party-picker" aria-label="Party size">
            <span>Party size</span>
            {data.restaurant.partySizes.map((size) => (
              <button className={size === partySize ? "active" : ""} key={size} onClick={() => setPartySize(size)}>{size}</button>
            ))}
          </div>
        </div>

        <article className="wait-card" aria-label="Current wait status">
          <div className="card-topline">
            <span>CURRENT WAIT</span>
            <span className={`status-pill status-${latest?.status ?? "unknown"}`}>
              {latest ? statusCopy[latest.status] : "Awaiting first reading"}
            </span>
          </div>
          <div className="wait-value">{currentWait(latest)}</div>
          <p className="wait-label">
            {latest ? `Recorded ${formatTime(latest.observedAt)}` : "No manual reading has been recorded yet."}
          </p>
          {latest?.errorMessage ? <p className="source-note">{latest.errorMessage}</p> : null}
          <div className="card-rule" />
          <div className="restaurant-row">
            <div><p className="micro-label">RESTAURANT</p><p>{data.restaurant.name}</p></div>
            <div><p className="micro-label">PARTY</p><p>{partySize} guests</p></div>
          </div>
          <div className="card-actions">
            <a className="primary-button" href={data.restaurant.waitSourceUrl} rel="noreferrer" target="_blank">1. Open official waitlist <span aria-hidden="true">↗</span></a>
            <form className="manual-entry" onSubmit={saveManualReading}>
              <div className="manual-heading">
                <div><span>2.</span><strong>Record what you see</strong></div>
                <small>Saved with the current time</small>
              </div>
              <label className="status-field">
                <span>Status</span>
                <select value={entryStatus} onChange={(event) => setEntryStatus(event.target.value)}>
                  <option value="wait_available">Wait shown</option>
                  <option value="no_wait">No wait</option>
                  <option value="waitlist_closed">Waitlist closed</option>
                  <option value="restaurant_closed">Restaurant closed</option>
                </select>
              </label>
              {entryStatus === "wait_available" ? (
                <div className="wait-fields">
                  <label><span>Minimum minutes</span><input aria-label="Minimum wait in minutes" inputMode="numeric" max="360" min="0" onChange={(event) => setWaitMin(event.target.value)} placeholder="45" required type="number" value={waitMin} /></label>
                  <label><span>Maximum (optional)</span><input aria-label="Maximum wait in minutes" inputMode="numeric" max="360" min="0" onChange={(event) => setWaitMax(event.target.value)} placeholder="60" type="number" value={waitMax} /></label>
                </div>
              ) : null}
              <button className="save-button" disabled={saveState === "loading"} type="submit">
                {saveState === "loading" ? "Saving…" : saveState === "done" ? "Saved" : "Save manual reading"}
              </button>
              {saveError ? <p className="entry-error" role="alert">{saveError}</p> : null}
            </form>
          </div>
        </article>
      </section>

      <section className="signal-strip" aria-label="Service status">
        <div><span>01</span><strong>Official handoff</strong><small>Never joins automatically</small></div>
        <div><span>02</span><strong>Manual check-ins</strong><small>No automated Yelp requests</small></div>
        <div><span>03</span><strong>{recommendation.confidence} confidence</strong><small>{recommendation.sampleCount} usable readings</small></div>
      </section>

      <section className="insights" id="history">
        <div className="section-heading">
          <div><p className="eyebrow">RECENT SIGNAL</p><h2>Wait history</h2></div>
          <p>Party of {partySize} · last 24 usable readings</p>
        </div>
        <HistoryChart observations={observations} />
        <div className="insight-grid">
          <article><p className="micro-label">MEDIAN WAIT</p><strong>{recommendation.p50Minutes === null ? "—" : `${recommendation.p50Minutes} min`}</strong></article>
          <article><p className="micro-label">SAFER BUFFER</p><strong>{recommendation.p80Minutes === null ? "—" : `${recommendation.p80Minutes} min`}</strong></article>
          <article className="recommendation-card"><p className="micro-label">RECOMMENDATION</p><p>{recommendation.message}</p></article>
        </div>
      </section>

      <footer>
        <strong>RESTO<span>WAIT</span>LIST</strong>
        <p>Independent timing tool. Not affiliated with Yelp or Din Tai Fung.</p>
        <a href={data.restaurant.officialUrl} target="_blank" rel="noreferrer">Restaurant details ↗</a>
      </footer>
    </main>
  );
}
