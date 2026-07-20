import { NextResponse } from "next/server";
import {
  getLatestObservation,
  initializeDatabase,
  listRestaurants,
} from "@/db/storage";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await initializeDatabase();
    const restaurants = await listRestaurants();
    const observations = await Promise.all(
      restaurants.map(async (restaurant) => {
        const partySize = restaurant.partySizes[0];
        const latest = partySize
          ? await getLatestObservation(restaurant.id, partySize)
          : null;
        return {
          slug: restaurant.slug,
          active: restaurant.active,
          partySize,
          latestStatus: latest?.status ?? "never_collected",
          lastObservedAt: latest?.observedAt ?? null,
        };
      }),
    );
    return NextResponse.json(
      {
        status: "ok",
        database: "connected",
        restaurantCount: restaurants.length,
        mode: "manual",
        observations,
        checkedAt: new Date().toISOString(),
      },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return NextResponse.json(
      { status: "degraded", database: "unavailable", checkedAt: new Date().toISOString() },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}
