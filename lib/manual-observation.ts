import type { ObservationStatus, Restaurant } from "@/lib/types";
import type { ObservationInput } from "@/db/storage";

export type ManualObservationPayload = {
  partySize?: unknown;
  status?: unknown;
  waitMinMinutes?: unknown;
  waitMaxMinutes?: unknown;
};

const CLOSED_STATUSES = new Set<ObservationStatus>([
  "waitlist_closed",
  "restaurant_closed",
]);

function optionalInteger(value: unknown): number | null {
  if (value === "" || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isInteger(number) ? number : null;
}

export function buildManualObservation(
  restaurant: Restaurant,
  payload: ManualObservationPayload,
  observedAt = new Date().toISOString(),
): ObservationInput {
  const partySize = optionalInteger(payload.partySize);
  if (partySize === null || !restaurant.partySizes.includes(partySize)) {
    throw new Error("Choose a supported party size");
  }

  const requestedStatus = String(payload.status ?? "wait_available") as ObservationStatus;
  if (requestedStatus === "no_wait") {
    return {
      partySize,
      observedAt,
      status: "no_wait",
      waitMinMinutes: 0,
      waitMaxMinutes: 0,
      waitMidpointMinutes: 0,
      rawWaitText: "No wait",
      sourceUrl: restaurant.waitSourceUrl,
      sourceProvider: `Manual entry · ${restaurant.provider}`,
      responseStatusCode: null,
      responseDurationMs: null,
      errorMessage: null,
      synthetic: false,
    };
  }

  if (CLOSED_STATUSES.has(requestedStatus)) {
    const label =
      requestedStatus === "restaurant_closed" ? "Restaurant closed" : "Waitlist closed";
    return {
      partySize,
      observedAt,
      status: requestedStatus,
      waitMinMinutes: null,
      waitMaxMinutes: null,
      waitMidpointMinutes: null,
      rawWaitText: label,
      sourceUrl: restaurant.waitSourceUrl,
      sourceProvider: `Manual entry · ${restaurant.provider}`,
      responseStatusCode: null,
      responseDurationMs: null,
      errorMessage: null,
      synthetic: false,
    };
  }

  if (requestedStatus !== "wait_available") {
    throw new Error("Choose a valid wait status");
  }

  const waitMinMinutes = optionalInteger(payload.waitMinMinutes);
  const enteredMax = optionalInteger(payload.waitMaxMinutes);
  if (waitMinMinutes === null || waitMinMinutes < 0 || waitMinMinutes > 360) {
    throw new Error("Enter a minimum wait between 0 and 360 minutes");
  }
  if (
    payload.waitMaxMinutes !== "" &&
    payload.waitMaxMinutes !== null &&
    payload.waitMaxMinutes !== undefined &&
    enteredMax === null
  ) {
    throw new Error("Maximum wait must be a whole number of minutes");
  }
  const waitMaxMinutes = enteredMax ?? waitMinMinutes;
  if (waitMaxMinutes < waitMinMinutes || waitMaxMinutes > 360) {
    throw new Error("Maximum wait must be between the minimum and 360 minutes");
  }

  return {
    partySize,
    observedAt,
    status: "manual",
    waitMinMinutes,
    waitMaxMinutes,
    waitMidpointMinutes: (waitMinMinutes + waitMaxMinutes) / 2,
    rawWaitText:
      waitMinMinutes === waitMaxMinutes
        ? `${waitMinMinutes} min`
        : `${waitMinMinutes}–${waitMaxMinutes} min`,
    sourceUrl: restaurant.waitSourceUrl,
    sourceProvider: `Manual entry · ${restaurant.provider}`,
    responseStatusCode: null,
    responseDurationMs: null,
    errorMessage: null,
    synthetic: false,
  };
}
