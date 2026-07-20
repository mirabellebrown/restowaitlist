import assert from "node:assert/strict";
import test from "node:test";
import { confirmedDinTaiFungObservations } from "../lib/confirmed-observations.ts";

test("keeps the four confirmed Din Tai Fung observations", () => {
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
    ],
  );
});
