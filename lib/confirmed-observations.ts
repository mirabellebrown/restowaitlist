import type { Observation } from "@/lib/types";

export const confirmedDinTaiFungObservations: Observation[] = [
  [1, "2026-07-20T19:30:00.000Z", 45, 60],
  [2, "2026-07-20T19:44:00.000Z", 50, 65],
  [3, "2026-07-20T19:58:00.097Z", 105, 120],
  [4, "2026-07-20T20:02:06.012Z", 110, 125],
].map(([id, observedAt, waitMinMinutes, waitMaxMinutes]) => ({
  id: id as number,
  restaurantId: 1,
  partySize: 4,
  observedAt: observedAt as string,
  status: "manual",
  waitMinMinutes: waitMinMinutes as number,
  waitMaxMinutes: waitMaxMinutes as number,
  waitMidpointMinutes: ((waitMinMinutes as number) + (waitMaxMinutes as number)) / 2,
  rawWaitText: `${waitMinMinutes}–${waitMaxMinutes} min`,
  sourceUrl:
    "https://www.yelp.com/waitlist/din-tai-fung-new-york-3?party_size=4",
  sourceProvider: "Manual entry · Yelp Waitlist",
  responseStatusCode: null,
  responseDurationMs: null,
  errorMessage: null,
  synthetic: false,
}));
