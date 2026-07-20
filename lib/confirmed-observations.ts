import type { Observation } from "@/lib/types";

export const confirmedDinTaiFungObservations: Observation[] = [
  [1, "2026-07-20T19:30:00.000Z", 45, 60],
  [2, "2026-07-20T19:44:00.000Z", 50, 65],
  [3, "2026-07-20T19:58:00.097Z", 105, 120],
  [4, "2026-07-20T20:02:06.012Z", 110, 125],
  [5, "2026-07-20T20:08:25.084Z", 75, 95],
  [6, "2026-07-20T20:16:41.564Z", 75, 95],
  [7, "2026-07-20T20:20:03.935Z", 80, 100],
  [8, "2026-07-20T20:27:44.347Z", 95, 125],
  [9, "2026-07-20T20:28:00.942Z", 100, 130],
  [10, "2026-07-20T20:32:30.585Z", 95, 125],
  [11, "2026-07-20T20:42:18.514Z", 105, 135],
  [12, "2026-07-20T20:53:54.775Z", 105, 135],
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
