import { getLatestObservation, getRestaurant } from "@/db/storage";
import type { Observation } from "@/lib/types";

export type CollectionOutcome = {
  cached: boolean;
  observation: Observation;
};

/**
 * The hosted web runtime is intentionally read-only.
 *
 * Browser automation or server-side requests to a protected third-party
 * waitlist are not an acceptable collection method. The supported collector
 * lives on the operator's Mac, where `dtf-waitwatch capture` receives a
 * complete manual/authorized snapshot before GitHub Pages is updated.
 */
export async function refreshRestaurant(
  slug: string,
  options: { force?: boolean; partySize?: number } = {},
): Promise<CollectionOutcome> {
  const restaurant = await getRestaurant(slug);
  if (!restaurant) throw new Error("Restaurant not found");
  if (!restaurant.active) throw new Error("Restaurant collection is disabled");

  const partySize = options.partySize ?? restaurant.partySizes[0];
  if (!partySize || !restaurant.partySizes.includes(partySize)) {
    throw new Error("Unsupported party size for this restaurant");
  }
  const latest = await getLatestObservation(restaurant.id, partySize);
  if (!latest) {
    throw new Error(
      "Hosted collection is disabled. Use the local manual/authorized snapshot workflow instead.",
    );
  }
  return { cached: true, observation: latest };
}
