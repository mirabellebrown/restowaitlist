import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function disabledResponse() {
  return NextResponse.json(
    {
      error:
        "Automated collection is disabled. Record a manual observation from the restaurant dashboard.",
    },
    { status: 410 },
  );
}

export async function POST() {
  return disabledResponse();
}

export async function GET() {
  return disabledResponse();
}
