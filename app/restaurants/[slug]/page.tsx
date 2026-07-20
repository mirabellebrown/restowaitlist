import { notFound } from "next/navigation";
import { Dashboard } from "@/app/dashboard";
import { getRestaurantDashboard } from "@/db/storage";
import { refreshRestaurant } from "@/lib/collector";

export const dynamic = "force-dynamic";

export default async function RestaurantPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  await refreshRestaurant(slug).catch(() => null);
  const data = await getRestaurantDashboard(slug).catch(() => null);
  if (!data) notFound();
  return <Dashboard data={data} />;
}
