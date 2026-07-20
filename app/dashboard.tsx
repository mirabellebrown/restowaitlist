"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
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
  const [refreshState, setRefreshState] = useState<"idle" | "loading" | "done">("idle");
  const observations = useMemo(
    () => data.observations.filter((item) => item.partySize === partySize),
    [data.observations, partySize],
  );
  const latest = observations.at(-1);

  async function refresh() {
    setRefreshState("loading");
    try {
      await fetch(`/api/collect/${data.restaurant.slug}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ force: true, partySize }),
      });
      setRefreshState("done");
      window.setTimeout(() => window.location.reload(), 450);
    } catch {
      setRefreshState("idle");
    }
  }

  return (
    <main className="site-shell">
      <nav className="nav-wrap" aria-label="Primary navigation">
        <Link className="wordmark" href="/">RESTO<span>WAIT</span>LIST</Link>
        <div className="nav-links">
          <a href="#history">History</a>
          <Link href="/manage">Manage</Link>
          <span className={`live-dot ${latest?.status === "wait_available" ? "is-live" : ""}`} aria-hidden="true" />
          NYC
        </div>
      </nav>

      <section className="hero dashboard-hero">
        <div className="hero-copy">
          <p className="eyebrow">{data.restaurant.city} · PARTY OF {partySize}</p>
          <h1>Time the table.<br />Skip the guesswork.</h1>
          <p className="lede">Public wait signals, saved over time and turned into a calmer dinner plan.</p>
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
            {latest ? `Checked ${formatTime(latest.observedAt)}` : "The collector has not run yet."}
          </p>
          {latest?.errorMessage ? <p className="source-note">{latest.errorMessage}</p> : null}
          <div className="card-rule" />
          <div className="restaurant-row">
            <div><p className="micro-label">RESTAURANT</p><p>{data.restaurant.name}</p></div>
            <div><p className="micro-label">PARTY</p><p>{partySize} guests</p></div>
          </div>
          <div className="card-actions">
            <a className="primary-button" href={data.restaurant.waitSourceUrl} rel="noreferrer" target="_blank">Open official waitlist <span aria-hidden="true">↗</span></a>
            <button className="refresh-button" disabled={refreshState === "loading"} onClick={refresh}>
              {refreshState === "loading" ? "Checking…" : refreshState === "done" ? "Recorded" : "Refresh reading"}
            </button>
          </div>
        </article>
      </section>

      <section className="signal-strip" aria-label="Service status">
        <div><span>01</span><strong>Official handoff</strong><small>Never joins automatically</small></div>
        <div><span>02</span><strong>{data.restaurant.intervalMinutes}-minute cache</strong><small>Conservative collection</small></div>
        <div><span>03</span><strong>{data.recommendation.confidence} confidence</strong><small>{data.recommendation.sampleCount} usable readings</small></div>
      </section>

      <section className="insights" id="history">
        <div className="section-heading">
          <div><p className="eyebrow">RECENT SIGNAL</p><h2>Wait history</h2></div>
          <p>Party of {partySize} · last 24 usable readings</p>
        </div>
        <HistoryChart observations={observations} />
        <div className="insight-grid">
          <article><p className="micro-label">MEDIAN WAIT</p><strong>{data.recommendation.p50Minutes === null ? "—" : `${data.recommendation.p50Minutes} min`}</strong></article>
          <article><p className="micro-label">SAFER BUFFER</p><strong>{data.recommendation.p80Minutes === null ? "—" : `${data.recommendation.p80Minutes} min`}</strong></article>
          <article className="recommendation-card"><p className="micro-label">RECOMMENDATION</p><p>{data.recommendation.message}</p></article>
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
