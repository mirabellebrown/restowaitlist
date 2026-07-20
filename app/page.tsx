// Internal workspace sites can read the authenticated OpenAI user from the
// forwarded request headers:
//
// import { headers } from "next/headers";
//
// export default async function Home() {
//   const requestHeaders = await headers();
//   const email = requestHeaders.get("oai-authenticated-user-email");
//   const encodedFullName = requestHeaders.get("oai-authenticated-user-full-name");
//   const fullName =
//     encodedFullName &&
//     requestHeaders.get("oai-authenticated-user-full-name-encoding") ===
//       "percent-encoded-utf-8"
//       ? decodeURIComponent(encodedFullName)
//       : null;
//   const displayName = fullName ?? email;
//   // ...
// }

import { Dashboard } from "@/app/dashboard";
import { DTF_SLUG, getRestaurantDashboard } from "@/db/storage";
import { dinTaiFungSeed } from "@/lib/seed";

export const dynamic = "force-dynamic";

export default async function Home() {
  let data = dinTaiFungSeed;
  try {
    data = (await getRestaurantDashboard(DTF_SLUG)) ?? dinTaiFungSeed;
  } catch {
    // The static fallback keeps the service-status page useful during a
    // transient database outage. /api/health reports the underlying error.
  }
  return <Dashboard data={data} />;
}
