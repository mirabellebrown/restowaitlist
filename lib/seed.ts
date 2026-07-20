import { summarizeRecommendation } from "@/lib/recommendation";
import type { RestaurantDashboard } from "@/lib/types";

const collectedAt = "2026-07-20T17:00:00.000Z";

export const dinTaiFungSeed: RestaurantDashboard = {
  restaurant: {
    id: 1,
    slug: "din-tai-fung-new-york-3",
    name: "Din Tai Fung",
    city: "New York, NY",
    address: "1633 Broadway, New York, NY 10019",
    timezone: "America/New_York",
    officialUrl:
      "https://www.yelp.com/biz/din-tai-fung-new-york-3?osq=Restaurants",
    waitSourceUrl:
      "https://www.yelp.com/waitlist/din-tai-fung-new-york-3?party_size=4&utm_medium=waitlist_widget&utm_source=biz_details",
    provider: "Yelp Waitlist",
    partySizes: [4],
    intervalMinutes: 15,
    active: true,
    permissionReviewedAt: collectedAt,
    createdAt: collectedAt,
    updatedAt: collectedAt,
  },
  observations: [
    {
      id: 1,
      restaurantId: 1,
      partySize: 4,
      observedAt: collectedAt,
      status: "source_blocked",
      waitMinMinutes: null,
      waitMaxMinutes: null,
      waitMidpointMinutes: null,
      rawWaitText: "",
      sourceUrl:
        "https://www.yelp.com/waitlist/din-tai-fung-new-york-3?party_size=4&utm_medium=waitlist_widget&utm_source=biz_details",
      sourceProvider: "Yelp Waitlist",
      responseStatusCode: 403,
      responseDurationMs: null,
      errorMessage:
        "Yelp declined the initial automated request with HTTP 403. No bypass was attempted.",
      synthetic: false,
    },
  ],
  recommendation: summarizeRecommendation([]),
};
