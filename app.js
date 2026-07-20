const STATUS_LABELS = {
  no_wait: "No wait",
  waitlist_closed: "Waitlist closed",
  restaurant_closed: "Restaurant closed",
  temporarily_unavailable: "Unavailable",
  source_blocked: "Source blocked",
  parse_error: "Not recorded",
  network_error: "Network error",
  missed_due_to_downtime: "Not recorded",
};

const tableHead = document.querySelector("#table-head");
const tableBody = document.querySelector("#table-body");
const emptyState = document.querySelector("#empty-state");
const restaurantName = document.querySelector("#restaurant-name");
const metadata = document.querySelector("#metadata");
const rowCount = document.querySelector("#row-count");

function makeCell(tagName, text, className = "") {
  const cell = document.createElement(tagName);
  cell.textContent = text;
  if (className) cell.className = className;
  return cell;
}

function waitLabel(wait) {
  if (!wait) return "—";
  if (wait.status === "wait_available") {
    const low = wait.wait_min_minutes;
    const high = wait.wait_max_minutes;
    if (low === null || low === undefined) return wait.raw_wait_text || "—";
    if (high === null || high === undefined) return `${low}+ min`;
    return low === high ? `${low} min` : `${low}–${high} min`;
  }
  return STATUS_LABELS[wait.status] || wait.raw_wait_text || "—";
}

function localTimestamp(utcValue, timezone) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(utcValue));
}

function render(data) {
  const restaurant = data.restaurant || {};
  const partySizes = data.party_sizes || [2, 3, 4, 5, 6];
  const rows = data.rows || [];
  const timezone = restaurant.timezone || "America/New_York";
  restaurantName.textContent = restaurant.name || "Wait table";
  document.title = `${restaurantName.textContent} wait table`;
  const latestObservation = data.latest_observation_at_utc || data.generated_at_utc;
  metadata.textContent = latestObservation
    ? `Latest observation ${localTimestamp(latestObservation, timezone)} (${timezone})`
    : `No observations published yet (${timezone})`;
  rowCount.textContent = rows.length ? `${rows.length} timestamps` : "";

  const headRow = document.createElement("tr");
  headRow.append(makeCell("th", "Date and time"));
  partySizes.forEach((partySize) => headRow.append(makeCell("th", `Party ${partySize}`)));
  tableHead.replaceChildren(headRow);

  const fragment = document.createDocumentFragment();
  rows.forEach((row) => {
    const tableRow = document.createElement("tr");
    tableRow.append(makeCell("td", localTimestamp(row.scheduled_at_utc, timezone), "timestamp"));
    partySizes.forEach((partySize) => {
      const wait = row.waits?.[String(partySize)];
      const cell = makeCell("td", waitLabel(wait), wait?.status || "missing");
      if (wait?.raw_wait_text) cell.title = wait.raw_wait_text;
      tableRow.append(cell);
    });
    fragment.append(tableRow);
  });
  tableBody.replaceChildren(fragment);
  emptyState.hidden = rows.length > 0;
}

async function loadData() {
  try {
    const response = await fetch(`data/waits.json?updated=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`waits.json returned ${response.status}`);
    return await response.json();
  } catch {
    const response = await fetch("data/empty-waits.json");
    return await response.json();
  }
}

loadData().then(render).catch(() => {
  metadata.textContent = "Published data is temporarily unavailable.";
  emptyState.hidden = false;
});
