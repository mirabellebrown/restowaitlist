import { env } from "cloudflare:workers";
import { NextResponse } from "next/server";
import { getChatGPTUser } from "@/app/chatgpt-auth";
import { refreshRestaurant } from "@/lib/collector";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ slug: string }> };

function authorizedCron(request: Request): boolean {
  const expected = env.CRON_SECRET;
  if (!expected) return false;
  return request.headers.get("authorization") === `Bearer ${expected}`;
}

async function collect(
  request: Request,
  context: RouteContext,
  requireUser: boolean,
) {
  if (requireUser) {
    const user = await getChatGPTUser();
    if (!user && process.env.NODE_ENV !== "development") {
      return NextResponse.json({ error: "Sign in is required" }, { status: 401 });
    }
  } else if (!authorizedCron(request)) {
    return NextResponse.json({ error: "Invalid scheduler credential" }, { status: 401 });
  }

  const { slug } = await context.params;
  const payload = request.method === "POST" ? await request.json().catch(() => ({})) : {};
  try {
    const result = await refreshRestaurant(slug, {
      force: Boolean(payload.force),
      partySize: typeof payload.partySize === "number" ? payload.partySize : undefined,
    });
    return NextResponse.json(result, {
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const status = message === "Restaurant not found" ? 404 : 400;
    return NextResponse.json({ error: message }, { status });
  }
}

export async function POST(request: Request, context: RouteContext) {
  return collect(request, context, true);
}

export async function GET(request: Request, context: RouteContext) {
  return collect(request, context, false);
}
