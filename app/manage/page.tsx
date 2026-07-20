import { requireChatGPTUser } from "@/app/chatgpt-auth";
import { listRestaurants } from "@/db/storage";
import { ManageClient } from "@/app/manage/manage-client";

export const dynamic = "force-dynamic";

export default async function ManagePage() {
  const user = await requireChatGPTUser("/manage");
  const restaurants = await listRestaurants();
  return <ManageClient initialRestaurants={restaurants} displayName={user.displayName} />;
}
