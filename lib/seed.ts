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
      "https://www.yelp.com/waitlist/din-tai-fung-new-york-3?party_size=4",
    provider: "Yelp Waitlist",
    partySizes: [4],
    intervalMinutes: 15,
    active: true,
    permissionReviewedAt: collectedAt,
    createdAt: collectedAt,
    updatedAt: collectedAt,
  },
  observations: [],
  recommendation: summarizeRecommendation([]),
};
