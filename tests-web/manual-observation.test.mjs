import assert from "node:assert/strict";
import test from "node:test";
import { buildManualObservation } from "../lib/manual-observation.ts";

const restaurant = {
  id: 1,
  slug: "test-restaurant",
  name: "Test Restaurant",
  city: "New York, NY",
  address: "1 Test Street",
  timezone: "America/New_York",
  officialUrl: "https://example.com/restaurant",
  waitSourceUrl: "https://example.com/waitlist?party_size=4",
  provider: "Official waitlist",
  partySizes: [2, 4],
  intervalMinutes: 15,
  active: true,
  permissionReviewedAt: null,
  createdAt: "2026-07-20T12:00:00.000Z",
  updatedAt: "2026-07-20T12:00:00.000Z",
};

test("builds a manual wait range", () => {
  const observation = buildManualObservation(
    restaurant,
    { partySize: 4, status: "wait_available", waitMinMinutes: 45, waitMaxMinutes: 60 },
    "2026-07-20T18:00:00.000Z",
  );
  assert.equal(observation.status, "manual");
  assert.equal(observation.waitMidpointMinutes, 52.5);
  assert.equal(observation.rawWaitText, "45–60 min");
});

test("records no wait as zero minutes", () => {
  const observation = buildManualObservation(
    restaurant,
    { partySize: 2, status: "no_wait" },
  );
  assert.equal(observation.status, "no_wait");
  assert.equal(observation.waitMidpointMinutes, 0);
});

test("rejects an inverted wait range", () => {
  assert.throws(
    () =>
      buildManualObservation(restaurant, {
        partySize: 4,
        status: "wait_available",
        waitMinMinutes: 90,
        waitMaxMinutes: 30,
      }),
    /Maximum wait/,
  );
});
