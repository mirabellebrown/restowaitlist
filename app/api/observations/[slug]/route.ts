import { NextResponse } from "next/server";
import { getChatGPTUser } from "@/app/chatgpt-auth";
import {
  getLatestObservation,
  getRestaurant,
  insertObservation,
} from "@/db/storage";
import {
  buildManualObservation,
  type ManualObservationPayload,
} from "@/lib/manual-observation";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ slug: string }> };

export async function POST(request: Request, context: RouteContext) {
  const user = await getChatGPTUser();
  const hostname = new URL(request.url).hostname;
  const localPreview = hostname === "127.0.0.1" || hostname === "localhost" || hostname === "[::1]";
  if (!user && !localPreview && process.env.NODE_ENV !== "development") {
    return NextResponse.json({ error: "Sign in is required" }, { status: 401 });
  }

  const { slug } = await context.params;
  const restaurant = await getRestaurant(slug).catch(() => null);
  if (!restaurant) {
    return NextResponse.json({ error: "Restaurant not found" }, { status: 404 });
  }

  const payload = (await request.json().catch(() => null)) as ManualObservationPayload | null;
  if (!payload) {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  try {
    const observation = buildManualObservation(restaurant, payload);
    await insertObservation(restaurant.id, observation);
    const saved = await getLatestObservation(restaurant.id, observation.partySize);
    return NextResponse.json(
      { observation: saved },
      { status: 201, headers: { "cache-control": "no-store" } },
    );
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 400 },
    );
  }
}
