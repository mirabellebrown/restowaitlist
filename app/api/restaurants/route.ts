import { NextResponse } from "next/server";
import { getChatGPTUser } from "@/app/chatgpt-auth";
import { listRestaurants, upsertRestaurant } from "@/db/storage";

export const dynamic = "force-dynamic";

function isPublicHttpsUrl(value: string): boolean {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:") return false;
    const hostname = url.hostname.toLowerCase();
    return !(
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "::1" ||
      hostname.endsWith(".local") ||
      /^10\./.test(hostname) ||
      /^192\.168\./.test(hostname) ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(hostname)
    );
  } catch {
    return false;
  }
}

export async function GET() {
  try {
    return NextResponse.json({ restaurants: await listRestaurants() });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  const user = await getChatGPTUser();
  if (!user && process.env.NODE_ENV !== "development") {
    return NextResponse.json({ error: "Sign in is required" }, { status: 401 });
  }

  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body) return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });

  const slug = String(body.slug ?? "").trim().toLowerCase();
  const name = String(body.name ?? "").trim();
  const officialUrl = String(body.officialUrl ?? "").trim();
  const waitSourceUrl = String(body.waitSourceUrl ?? "").trim();
  const partySizes = Array.isArray(body.partySizes)
    ? body.partySizes.map(Number).filter((size) => Number.isInteger(size) && size >= 1 && size <= 20)
    : [];

  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
    return NextResponse.json({ error: "Slug must contain lowercase words and hyphens" }, { status: 400 });
  }
  if (!name || !isPublicHttpsUrl(officialUrl) || !isPublicHttpsUrl(waitSourceUrl)) {
    return NextResponse.json({ error: "Name and public HTTPS URLs are required" }, { status: 400 });
  }
  if (!partySizes.length) {
    return NextResponse.json({ error: "At least one party size is required" }, { status: 400 });
  }

  try {
    const restaurant = await upsertRestaurant({
      slug,
      name,
      city: String(body.city ?? "").trim(),
      address: String(body.address ?? "").trim(),
      timezone: String(body.timezone ?? "America/New_York").trim(),
      officialUrl,
      waitSourceUrl,
      provider: String(body.provider ?? "Configured public source").trim(),
      partySizes: [...new Set(partySizes)].sort((a, b) => a - b),
      intervalMinutes: Math.min(1440, Math.max(15, Number(body.intervalMinutes) || 15)),
      active: body.active !== false,
      permissionReviewedAt: body.permissionAcknowledged ? new Date().toISOString() : null,
    });
    return NextResponse.json({ restaurant }, { status: 201 });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 400 },
    );
  }
}
