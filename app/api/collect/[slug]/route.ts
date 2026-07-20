import { NextResponse } from "next/server";
import { env } from "cloudflare:workers";
import {
  getRestaurant,
  insertObservation,
  listObservations,
  type ObservationInput,
} from "@/db/storage";
import type { ObservationStatus } from "@/lib/types";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ slug: string }> };
type RawObservation = Record<string, unknown>;

// Statuses an automated reader may report. "manual" is intentionally excluded —
// that path stays owned by the signed-in dashboard form.
const AUTOMATED_STATUSES = new Set<ObservationStatus>([
  "wait_available",
  "no_wait",
  "waitlist_closed",
  "restaurant_closed",
  "temporarily_unavailable",
  "source_blocked",
  "parse_error",
  "network_error",
]);

const MAX_WAIT_MINUTES = 1440;
const MAX_BATCH = 50;

/**
 * Read a secret from the Worker binding (Cloudflare) or process.env (dev/preview).
 * Enables automated ingestion only when COLLECTOR_TOKEN is configured.
 */
function readSecret(name: string): string | undefined {
  try {
    const value = (env as unknown as Record<string, unknown>)[name];
    if (typeof value === "string" && value.length > 0) return value;
  } catch {
    // env binding is unavailable outside the Worker runtime; fall through.
  }
  if (typeof process !== "undefined" && process.env && process.env[name]) {
    return process.env[name];
  }
  return undefined;
}

function providedToken(request: Request): string | null {
  const header = request.headers.get("authorization") ?? "";
  if (header.startsWith("Bearer ")) return header.slice(7).trim();
  const alt = request.headers.get("x-collector-token");
  return alt ? alt.trim() : null;
}

function optionalInt(value: unknown): number | null {
  if (value === "" || value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isInteger(n) ? n : null;
}

function buildAutomatedObservation(
  restaurant: { waitSourceUrl: string; provider: string },
  raw: RawObservation,
  nowMs: number,
): ObservationInput {
  const partySize = optionalInt(raw.partySize);
  if (partySize === null || partySize < 1 || partySize > 20) {
    throw new Error("partySize must be an integer between 1 and 20");
  }

  const status = String(raw.status ?? "wait_available") as ObservationStatus;
  if (!AUTOMATED_STATUSES.has(status)) {
    throw new Error(`Unsupported status: ${status}`);
  }

  const observedAt = String(raw.observedAt ?? new Date(nowMs).toISOString());
  const observedDate = new Date(observedAt);
  if (Number.isNaN(observedDate.getTime())) {
    throw new Error("observedAt must be a valid date/time");
  }
  if (observedDate.getTime() > nowMs + 10 * 60_000) {
    throw new Error("observedAt cannot be in the future");
  }

  let waitMin = optionalInt(raw.waitMinMinutes);
  let waitMax = optionalInt(raw.waitMaxMinutes);
  let midpoint: number | null = null;

  if (status === "wait_available" || status === "no_wait") {
    if (status === "no_wait") {
      waitMin = 0;
      waitMax = 0;
    }
    if (waitMin === null) throw new Error("waitMinMinutes is required for wait_available");
    if (waitMax === null) waitMax = waitMin;
    if (waitMin < 0 || waitMax < waitMin || waitMax > MAX_WAIT_MINUTES) {
      throw new Error("wait minutes are out of range");
    }
    midpoint = (waitMin + waitMax) / 2;
  } else {
    waitMin = null;
    waitMax = null;
  }

  const rawText =
    typeof raw.rawWaitText === "string" && raw.rawWaitText.length > 0
      ? raw.rawWaitText
      : status.replace(/_/g, " ");
  const sourceUrl =
    typeof raw.sourceUrl === "string" && raw.sourceUrl.length > 0
      ? raw.sourceUrl
      : restaurant.waitSourceUrl;

  return {
    partySize,
    observedAt: observedDate.toISOString(),
    status,
    waitMinMinutes: waitMin,
    waitMaxMinutes: waitMax,
    waitMidpointMinutes: midpoint,
    rawWaitText: rawText,
    sourceUrl,
    sourceProvider: `Automated · ${restaurant.provider}`,
    responseStatusCode: optionalInt(raw.responseStatusCode),
    responseDurationMs: optionalInt(raw.responseDurationMs),
    errorMessage: typeof raw.errorMessage === "string" ? raw.errorMessage : null,
    synthetic: false,
  };
}

export async function POST(request: Request, context: RouteContext) {
  const configured = readSecret("COLLECTOR_TOKEN");
  if (!configured) {
    return NextResponse.json(
      {
        error:
          "Automated collection is not configured. Set the COLLECTOR_TOKEN secret to enable this endpoint.",
      },
      { status: 503 },
    );
  }

  const provided = providedToken(request);
  if (!provided || provided !== configured) {
    return NextResponse.json({ error: "Invalid or missing collector token" }, { status: 401 });
  }

  const { slug } = await context.params;
  const restaurant = await getRestaurant(slug).catch(() => null);
  if (!restaurant) {
    return NextResponse.json({ error: "Restaurant not found" }, { status: 404 });
  }

  const body = (await request.json().catch(() => null)) as
    | { observations?: RawObservation[] }
    | RawObservation[]
    | null;
  const items = Array.isArray(body) ? body : body?.observations;
  if (!Array.isArray(items) || items.length === 0) {
    return NextResponse.json(
      { error: "Body must be a non-empty array of observations or { observations: [...] }" },
      { status: 400 },
    );
  }
  if (items.length > MAX_BATCH) {
    return NextResponse.json(
      { error: `Too many observations in one request (max ${MAX_BATCH})` },
      { status: 400 },
    );
  }

  const nowMs = Date.now();
  const accepted: ObservationInput[] = [];
  const rejected: { index: number; error: string }[] = [];

  items.forEach((item, index) => {
    try {
      accepted.push(buildAutomatedObservation(restaurant, item, nowMs));
    } catch (error) {
      rejected.push({ index, error: error instanceof Error ? error.message : String(error) });
    }
  });

  for (const observation of accepted) {
    await insertObservation(restaurant.id, observation);
  }

  const latest = await listObservations(restaurant.id, 40);
  const ok = accepted.length > 0;
  // "accepted" = observations that validated and were upserted. Rows duplicating
  // an existing (party size, 15-min slot) are ignored, so re-runs are idempotent.
  return NextResponse.json(
    { accepted: accepted.length, rejected, latest },
    { status: ok ? 201 : 400, headers: { "cache-control": "no-store" } },
  );
}

export async function GET() {
  return NextResponse.json(
    {
      endpoint: "collect",
      method: "POST",
      auth: "Authorization: Bearer <COLLECTOR_TOKEN>",
      body: '{ "observations": [{ "partySize": 4, "status": "wait_available", "waitMinMinutes": 45, "waitMaxMinutes": 60, "observedAt": "ISO-8601" }] }',
    },
    { status: 200 },
  );
}
