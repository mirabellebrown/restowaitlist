import type { Observation, RecommendationSummary } from "@/lib/types";

function percentile(values: number[], fraction: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

export function summarizeRecommendation(
  observations: Observation[],
): RecommendationSummary {
  const waits = observations.flatMap((observation) =>
    (observation.status === "wait_available" ||
      observation.status === "manual" ||
      observation.status === "no_wait") &&
    observation.waitMidpointMinutes !== null
      ? [observation.waitMidpointMinutes]
      : [],
  );
  const targetSamples = 24;

  if (waits.length < 6) {
    return {
      confidence: "building",
      sampleCount: waits.length,
      targetSamples,
      p50Minutes: waits.length ? Math.round(percentile(waits, 0.5)) : null,
      p80Minutes: waits.length ? Math.round(percentile(waits, 0.8)) : null,
      message: `Collect ${Math.max(0, targetSamples - waits.length)} more usable readings for a timing recommendation.`,
    };
  }

  const confidence = waits.length >= 72 ? "high" : waits.length >= 24 ? "medium" : "low";
  const p50Minutes = Math.round(percentile(waits, 0.5));
  const p80Minutes = Math.round(percentile(waits, 0.8));
  return {
    confidence,
    sampleCount: waits.length,
    targetSamples,
    p50Minutes,
    p80Minutes,
    message: `For a safer arrival, allow about ${p80Minutes} minutes between joining and your target table time.`,
  };
}
