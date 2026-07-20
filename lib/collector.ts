import {
  getLatestObservation,
  getRestaurant,
  insertObservation,
  type ObservationInput,
} from "@/db/storage";
import type { Observation, Restaurant } from "@/lib/types";
import { parseWaitHtml } from "@/lib/wait-parser";

const BLOCK_STATUS_CODES = new Set([401, 403, 429]);
const BLOCK_MARKERS = [
  "captcha",
  "are you a robot",
  "verify you are human",
  "unusual traffic",
  "access denied",
  "bot detection",
];

export type CollectionOutcome = {
  cached: boolean;
  observation: ObservationInput | Observation;
};

function blankObservation(
  restaurant: Restaurant,
  partySize: number,
  observedAt: string,
  duration: number,
  status: ObservationInput["status"],
  errorMessage: string,
  responseStatusCode: number | null = null,
): ObservationInput {
  return {
    partySize,
    observedAt,
    status,
    waitMinMinutes: null,
    waitMaxMinutes: null,
    waitMidpointMinutes: null,
    rawWaitText: "",
    sourceUrl: restaurant.waitSourceUrl,
    sourceProvider: restaurant.provider,
    responseStatusCode,
    responseDurationMs: duration,
    errorMessage,
    synthetic: false,
  };
}

async function collectOnce(
  restaurant: Restaurant,
  partySize: number,
): Promise<ObservationInput> {
  const started = performance.now();
  const observedAt = new Date().toISOString();
  try {
    const response = await fetch(restaurant.waitSourceUrl, {
      headers: {
        "user-agent":
          "restowaitlist/0.2 (permission-aware restaurant wait monitor)",
        accept: "text/html,application/xhtml+xml",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(15_000),
    });
    const duration = Math.round(performance.now() - started);
    const body = (await response.text()).slice(0, 500_000);
    const lower = body.slice(0, 100_000).toLowerCase();

    if (
      BLOCK_STATUS_CODES.has(response.status) ||
      BLOCK_MARKERS.some((marker) => lower.includes(marker))
    ) {
      return blankObservation(
        restaurant,
        partySize,
        observedAt,
        duration,
        "source_blocked",
        `The source declined automated access (HTTP ${response.status}). No bypass or further retry was attempted.`,
        response.status,
      );
    }

    if (response.status >= 500) {
      return blankObservation(
        restaurant,
        partySize,
        observedAt,
        duration,
        "temporarily_unavailable",
        `The source returned HTTP ${response.status}.`,
        response.status,
      );
    }

    if (!response.ok) {
      return blankObservation(
        restaurant,
        partySize,
        observedAt,
        duration,
        "network_error",
        `The source returned HTTP ${response.status}.`,
        response.status,
      );
    }

    const parsed = parseWaitHtml(body);
    return {
      partySize,
      observedAt,
      ...parsed,
      sourceUrl: restaurant.waitSourceUrl,
      sourceProvider: restaurant.provider,
      responseStatusCode: response.status,
      responseDurationMs: duration,
      synthetic: false,
    };
  } catch (error) {
    const duration = Math.round(performance.now() - started);
    return blankObservation(
      restaurant,
      partySize,
      observedAt,
      duration,
      "network_error",
      `The source request failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

export async function refreshRestaurant(
  slug: string,
  options: { force?: boolean; partySize?: number } = {},
): Promise<CollectionOutcome> {
  const restaurant = await getRestaurant(slug);
  if (!restaurant) throw new Error("Restaurant not found");
  if (!restaurant.active) throw new Error("Restaurant collection is disabled");
  if (!restaurant.permissionReviewedAt) {
    throw new Error("Automated collection permission has not been reviewed");
  }

  const partySize = options.partySize ?? restaurant.partySizes[0];
  if (!restaurant.partySizes.includes(partySize)) {
    throw new Error("Unsupported party size for this restaurant");
  }

  const latest = await getLatestObservation(restaurant.id, partySize);
  const staleAfter = restaurant.intervalMinutes * 60_000;
  if (
    !options.force &&
    latest &&
    Date.now() - new Date(latest.observedAt).getTime() < staleAfter
  ) {
    return { cached: true, observation: latest };
  }

  const observation = await collectOnce(restaurant, partySize);
  await insertObservation(restaurant.id, observation);
  return { cached: false, observation };
}
