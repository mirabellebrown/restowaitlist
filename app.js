const STATUS_COPY = {
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

const WAITLIST_URL =
  "https://www.yelp.com/waitlist/din-tai-fung-new-york-3?party_size=";

const els = {
  liveDot: document.querySelector("#live-dot"),
  eyebrow: document.querySelector("#hero-eyebrow"),
  partyPicker: document.querySelector("#party-picker"),
  statusPill: document.querySelector("#status-pill"),
  waitValue: document.querySelector("#wait-value"),
  waitLabel: document.querySelector("#wait-label"),
  sourceNote: document.querySelector("#source-note"),
  restaurantName: document.querySelector("#restaurant-name"),
  partyLabel: document.querySelector("#party-label"),
  waitlistLink: document.querySelector("#waitlist-link"),
  confidence: document.querySelector("#confidence-label"),
  samples: document.querySelector("#sample-label"),
  historyCaption: document.querySelector("#history-caption"),
  chart: document.querySelector("#history-chart"),
  p50: document.querySelector("#p50"),
  p80: document.querySelector("#p80"),
  recommendation: document.querySelector("#recommendation"),
  officialLink: document.querySelector("#official-link"),
};

let state = {
  partySize: 4,
  timezone: "America/New_York",
  partySizes: [2, 3, 4, 5],
  observations: [],
};

function formatTime(value, timeZone) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(new Date(value));
}

function waitText(observation) {
  if (!observation) return "—";
  if (observation.status === "no_wait") return "0 min";
  if (observation.status === "waitlist_closed") return "Closed";
  if (observation.status === "restaurant_closed") return "Closed";
  if (observation.status === "temporarily_unavailable") return "Unavailable";
  if (observation.waitMinMinutes === null || observation.waitMinMinutes === undefined) {
    return STATUS_COPY[observation.status] || "—";
  }
  if (
    observation.waitMaxMinutes !== null &&
    observation.waitMaxMinutes !== undefined &&
    observation.waitMaxMinutes !== observation.waitMinMinutes
  ) {
    return `${observation.waitMinMinutes}–${observation.waitMaxMinutes} min`;
  }
  return `${observation.waitMinMinutes} min`;
}

const CHART_STATUSES = new Set([
  "wait_available",
  "manual",
  "no_wait",
  "waitlist_closed",
  "restaurant_closed",
  "temporarily_unavailable",
]);

function isNumericWait(item) {
  return (
    item.waitMidpointMinutes !== null &&
    item.waitMidpointMinutes !== undefined &&
    (item.status === "wait_available" ||
      item.status === "manual" ||
      item.status === "no_wait")
  );
}

function percentile(values, fraction) {
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

function summarize(observations) {
  const waits = observations.flatMap((item) =>
    (item.status === "wait_available" ||
      item.status === "manual" ||
      item.status === "no_wait") &&
    item.waitMidpointMinutes !== null &&
    item.waitMidpointMinutes !== undefined
      ? [item.waitMidpointMinutes]
      : [],
  );
  const targetSamples = 24;
  if (waits.length < 6) {
    return {
      confidence: "building",
      sampleCount: waits.length,
      p50Minutes: waits.length ? Math.round(percentile(waits, 0.5)) : null,
      p80Minutes: waits.length ? Math.round(percentile(waits, 0.8)) : null,
      message: `Collect ${Math.max(0, targetSamples - waits.length)} more usable readings for a timing recommendation.`,
    };
  }
  const confidence =
    waits.length >= 72 ? "high" : waits.length >= 24 ? "medium" : "low";
  const p50Minutes = Math.round(percentile(waits, 0.5));
  const p80Minutes = Math.round(percentile(waits, 0.8));
  return {
    confidence,
    sampleCount: waits.length,
    p50Minutes,
    p80Minutes,
    message: `For a safer arrival, allow about ${p80Minutes} minutes between joining and your target table time.`,
  };
}

function flattenRows(data) {
  const rows = data.rows || [];
  const observations = [];
  let id = 1;
  for (const row of rows) {
    const waits = row.waits || {};
    for (const [partySize, wait] of Object.entries(waits)) {
      const min = wait.wait_min_minutes ?? null;
      const max = wait.wait_max_minutes ?? null;
      const midpoint =
        min === null
          ? null
          : max === null
            ? min
            : (min + max) / 2;
      observations.push({
        id: id++,
        partySize: Number(partySize),
        observedAt: row.scheduled_at_utc,
        status: wait.status || "parse_error",
        waitMinMinutes: min,
        waitMaxMinutes: max,
        waitMidpointMinutes: midpoint,
        rawWaitText: wait.raw_wait_text || "",
        errorMessage: wait.error_message || null,
      });
    }
  }
  observations.sort((a, b) => a.observedAt.localeCompare(b.observedAt));
  return observations;
}

function renderChart(observations, timeZone) {
  const usable = observations
    .filter((item) => CHART_STATUSES.has(item.status))
    .slice(-24);

  if (usable.length < 1) {
    els.chart.className = "empty-chart";
    els.chart.innerHTML =
      '<div class="empty-line"></div><p>Wait history will appear after the first reading.</p>';
    return;
  }

  const numericValues = usable
    .filter(isNumericWait)
    .map((item) => item.waitMidpointMinutes ?? 0);
  const max = Math.max(...numericValues, 15);
  const plotPoints = usable.map((item, index) => {
    const x = usable.length === 1 ? 50 : (index / (usable.length - 1)) * 100;
    const numeric = isNumericWait(item);
    const y = numeric
      ? 92 - ((item.waitMidpointMinutes ?? 0) / max) * 76
      : 92; // closed / unavailable sit on the baseline
    return { item, x, y, numeric };
  });
  const linePoints = plotPoints.filter((point) => point.numeric);
  const points = linePoints.map(({ x, y }) => `${x},${y}`).join(" ");
  const fill =
    linePoints.length >= 2
      ? `<polyline class="chart-fill" points="0,100 ${points} 100,100"></polyline>
      <polyline class="chart-line" points="${points}"></polyline>`
      : linePoints.length === 1
        ? `<polyline class="chart-line" points="${points}"></polyline>`
        : "";

  els.chart.className = "history-chart";
  els.chart.innerHTML = `
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Recent wait history">
      ${fill}
    </svg>
    <div class="chart-points-layer"></div>
    <div class="chart-labels">
      <span>${formatTime(usable[0].observedAt, timeZone)}</span>
      <span>${formatTime(usable.at(-1).observedAt, timeZone)}</span>
    </div>
  `;

  const layer = els.chart.querySelector(".chart-points-layer");
  plotPoints.forEach(({ item, x, y, numeric }, index) => {
    const button = document.createElement("button");
    button.type = "button";
    const statusClass = numeric ? "" : ` point-status point-${item.status}`;
    button.className = `chart-point${statusClass}${index === 0 ? " point-start" : ""}${
      index === plotPoints.length - 1 ? " point-end" : ""
    }`;
    button.style.left = `${x}%`;
    button.style.top = `${y}%`;
    button.setAttribute(
      "aria-label",
      `${waitText(item)} at ${formatTime(item.observedAt, timeZone)}`,
    );
    button.innerHTML = `
      <span class="chart-tooltip">
        <strong>${waitText(item)}</strong>
        <span>${STATUS_COPY[item.status] || item.status}</span>
        <span>${formatTime(item.observedAt, timeZone)}</span>
      </span>
    `;
    layer.append(button);
  });
}

function renderPartyPicker() {
  const label = els.partyPicker.querySelector("span");
  els.partyPicker.replaceChildren(label);
  for (const size of state.partySizes) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = String(size);
    button.className = size === state.partySize ? "active" : "";
    button.addEventListener("click", () => {
      state.partySize = size;
      render();
    });
    els.partyPicker.append(button);
  }
}

function render() {
  const observations = state.observations.filter(
    (item) => item.partySize === state.partySize,
  );
  const latest = observations.at(-1);
  const recommendation = summarize(observations);

  els.eyebrow.textContent = `NEW YORK · PARTY OF ${state.partySize}`;
  els.partyLabel.textContent = `${state.partySize} guests`;
  els.waitlistLink.href = `${WAITLIST_URL}${state.partySize}`;
  els.historyCaption.textContent = `Party of ${state.partySize} · last 24 readings`;

  els.statusPill.textContent = latest
    ? STATUS_COPY[latest.status] || latest.status
    : "Awaiting first reading";
  els.statusPill.className = `status-pill status-${latest?.status ?? "unknown"}`;
  els.waitValue.textContent = waitText(latest);
  els.waitLabel.textContent = latest
    ? `Recorded ${formatTime(latest.observedAt, state.timezone)}`
    : "No reading has been published yet.";
  els.liveDot.classList.toggle("is-live", Boolean(latest));

  if (latest?.errorMessage) {
    els.sourceNote.hidden = false;
    els.sourceNote.textContent = latest.errorMessage;
  } else {
    els.sourceNote.hidden = true;
    els.sourceNote.textContent = "";
  }

  els.confidence.textContent = `${recommendation.confidence} confidence`;
  els.samples.textContent = `${recommendation.sampleCount} usable readings`;
  els.p50.textContent =
    recommendation.p50Minutes === null ? "—" : `${recommendation.p50Minutes} min`;
  els.p80.textContent =
    recommendation.p80Minutes === null ? "—" : `${recommendation.p80Minutes} min`;
  els.recommendation.textContent = recommendation.message;

  renderPartyPicker();
  renderChart(observations, state.timezone);
}

async function loadData() {
  try {
    const response = await fetch(`data/waits.json?updated=${Date.now()}`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`waits.json returned ${response.status}`);
    return await response.json();
  } catch {
    const response = await fetch("data/empty-waits.json");
    return await response.json();
  }
}

loadData()
  .then((data) => {
    const restaurant = data.restaurant || {};
    state.timezone = restaurant.timezone || "America/New_York";
    state.partySizes = data.party_sizes || [2, 3, 4, 5];
    if (!state.partySizes.includes(state.partySize)) {
      state.partySize = state.partySizes[0] ?? 4;
    }
    state.observations = flattenRows(data);
    els.restaurantName.textContent = restaurant.name || "Din Tai Fung New York";
    if (restaurant.official_url) {
      els.officialLink.href = restaurant.official_url;
    }
    document.title = `RestoWaitlist · ${els.restaurantName.textContent}`;
    render();
  })
  .catch(() => {
    els.waitLabel.textContent = "Published data is temporarily unavailable.";
    els.recommendation.textContent = "Try refreshing in a moment.";
    renderPartyPicker();
  });
