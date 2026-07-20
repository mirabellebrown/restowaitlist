import assert from "node:assert/strict";
import test from "node:test";
import { parseWaitHtml } from "../lib/wait-parser.ts";

test("parses a wait range near the wait label", () => {
  const result = parseWaitHtml("<main><p>Current wait time: 35–50 minutes</p></main>");
  assert.equal(result.status, "wait_available");
  assert.equal(result.waitMinMinutes, 35);
  assert.equal(result.waitMaxMinutes, 50);
  assert.equal(result.waitMidpointMinutes, 42.5);
});

test("parses a single minute estimate", () => {
  const result = parseWaitHtml("<div>Wait: 20 min</div>");
  assert.equal(result.status, "wait_available");
  assert.equal(result.waitMidpointMinutes, 20);
});

test("recognizes a closed waitlist", () => {
  const result = parseWaitHtml("<p>The waitlist is closed for tonight.</p>");
  assert.equal(result.status, "waitlist_closed");
});

test("does not parse numbers from script content", () => {
  const result = parseWaitHtml("<script>const wait = '45 minutes'</script><p>Welcome</p>");
  assert.equal(result.status, "parse_error");
});

test("recognizes no-wait text", () => {
  const result = parseWaitHtml("<p>Current wait time: no wait</p>");
  assert.equal(result.status, "no_wait");
  assert.equal(result.waitMidpointMinutes, 0);
});
