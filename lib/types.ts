export type ObservationStatus =
  | "wait_available"
  | "no_wait"
  | "waitlist_closed"
  | "restaurant_closed"
  | "temporarily_unavailable"
  | "source_blocked"
  | "parse_error"
  | "network_error"
  | "manual";

export type Restaurant = {
  id: number;
  slug: string;
  name: string;
  city: string;
  address: string;
  timezone: string;
  officialUrl: string;
  waitSourceUrl: string;
  provider: string;
  partySizes: number[];
  intervalMinutes: number;
  active: boolean;
  permissionReviewedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type Observation = {
  id: number;
  restaurantId: number;
  partySize: number;
  observedAt: string;
  status: ObservationStatus;
  waitMinMinutes: number | null;
  waitMaxMinutes: number | null;
  waitMidpointMinutes: number | null;
  rawWaitText: string;
  sourceUrl: string;
  sourceProvider: string;
  responseStatusCode: number | null;
  responseDurationMs: number | null;
  errorMessage: string | null;
  synthetic: boolean;
};

export type RecommendationSummary = {
  confidence: "building" | "low" | "medium" | "high";
  sampleCount: number;
  targetSamples: number;
  p50Minutes: number | null;
  p80Minutes: number | null;
  message: string;
};

export type RestaurantDashboard = {
  restaurant: Restaurant;
  observations: Observation[];
  recommendation: RecommendationSummary;
};
