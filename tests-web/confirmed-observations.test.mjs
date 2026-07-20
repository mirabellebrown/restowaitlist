import assert from "node:assert/strict";
import test from "node:test";
import { confirmedDinTaiFungObservations } from "../lib/confirmed-observations.ts";

test("keeps the twelve confirmed Din Tai Fung observations", () => {
  assert.deepEqual(
    confirmedDinTaiFungObservations.map((observation) => ({
      observedAt: observation.observedAt,
      partySize: observation.partySize,
      waitMinMinutes: observation.waitMinMinutes,
      waitMaxMinutes: observation.waitMaxMinutes,
    })),
    [
      { observedAt: "2026-07-20T19:30:00.000Z", partySize: 4, waitMinMinutes: 45, waitMaxMinutes: 60 },
      { observedAt: "2026-07-20T19:44:00.000Z", partySize: 4, waitMinMinutes: 50, waitMaxMinutes: 65 },
      { observedAt: "2026-07-20T19:58:00.097Z", partySize: 4, waitMinMinutes: 105, waitMaxMinutes: 120 },
      { observedAt: "2026-07-20T20:02:06.012Z", partySize: 4, waitMinMinutes: 110, waitMaxMinutes: 125 },
      { observedAt: "2026-07-20T20:08:25.084Z", partySize: 4, waitMinMinutes: 75, waitMaxMinutes: 95 },
      { observedAt: "2026-07-20T20:16:41.564Z", partySize: 4, waitMinMinutes: 75, waitMaxMinutes: 95 },
      { observedAt: "2026-07-20T20:20:03.935Z", partySize: 4, waitMinMinutes: 80, waitMaxMinutes: 100 },
      { observedAt: "2026-07-20T20:27:44.347Z", partySize: 4, waitMinMinutes: 95, waitMaxMinutes: 125 },
      { observedAt: "2026-07-20T20:28:00.942Z", partySize: 4, waitMinMinutes: 100, waitMaxMinutes: 130 },
      { observedAt: "2026-07-20T20:32:30.585Z", partySize: 4, waitMinMinutes: 95, waitMaxMinutes: 125 },
      { observedAt: "2026-07-20T20:42:18.514Z", partySize: 4, waitMinMinutes: 105, waitMaxMinutes: 135 },
      { observedAt: "2026-07-20T20:53:54.775Z", partySize: 4, waitMinMinutes: 105, waitMaxMinutes: 135 },
    ],
  );
});
