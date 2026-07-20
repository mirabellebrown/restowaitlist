"use client";

import Link from "next/link";
import { useState } from "react";
import type { Restaurant } from "@/lib/types";

export function ManageClient({
  initialRestaurants,
  displayName,
}: {
  initialRestaurants: Restaurant[];
  displayName: string;
}) {
  const [restaurants, setRestaurants] = useState(initialRestaurants);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  async function saveRestaurant(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/restaurants", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        slug: form.get("slug"),
        name: form.get("name"),
        city: form.get("city"),
        address: form.get("address"),
        timezone: form.get("timezone"),
        officialUrl: form.get("officialUrl"),
        waitSourceUrl: form.get("waitSourceUrl"),
        provider: form.get("provider"),
        partySizes: String(form.get("partySizes") ?? "")
          .split(",")
          .map((value) => Number(value.trim())),
        intervalMinutes: 15,
        permissionAcknowledged: false,
        active: true,
      }),
    });
    const result = (await response.json()) as { restaurant?: Restaurant; error?: string };
    if (!response.ok || !result.restaurant) {
      setMessage(result.error ?? "Restaurant could not be saved");
    } else {
      setRestaurants((current) => [
        ...current.filter((item) => item.slug !== result.restaurant!.slug),
        result.restaurant!,
      ].sort((a, b) => a.name.localeCompare(b.name)));
      setMessage(`${result.restaurant.name} saved.`);
      event.currentTarget.reset();
    }
    setSaving(false);
  }

  return (
    <main className="manage-shell">
      <nav className="manage-nav">
        <Link className="wordmark" href="/">RESTO<span>WAIT</span>LIST</Link>
        <div><span>Signed in as {displayName}</span><a href="/signout-with-chatgpt?return_to=/">Sign out</a></div>
      </nav>

      <header className="manage-header">
        <p className="eyebrow">MANUAL TRACKING</p>
        <h1>Restaurant waitlists</h1>
        <p>Add a restaurant and its public waitlist link. RestoWaitlist will save only the readings you enter yourself.</p>
      </header>

      <section className="manage-grid">
        <div className="restaurant-list">
          <h2>Configured</h2>
          {restaurants.map((restaurant) => (
            <article key={restaurant.slug}>
              <div>
                <strong>{restaurant.name}</strong>
                <p>{restaurant.city} · party {restaurant.partySizes.join(", ")}</p>
              </div>
              <div className="restaurant-state">
                <span className={restaurant.active ? "enabled" : "disabled"}>{restaurant.active ? "Active" : "Paused"}</span>
                <Link href={`/restaurants/${restaurant.slug}`}>View ↗</Link>
              </div>
            </article>
          ))}
        </div>

        <form className="restaurant-form" onSubmit={saveRestaurant}>
          <h2>Add or update</h2>
          <label>Restaurant name<input name="name" required placeholder="La Parisienne" /></label>
          <label>Slug<input name="slug" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="la-parisienne-new-york" /></label>
          <div className="form-pair">
            <label>City<input name="city" required placeholder="New York, NY" /></label>
            <label>Timezone<input name="timezone" defaultValue="America/New_York" required /></label>
          </div>
          <label>Address<input name="address" required placeholder="9 Maiden Lane, New York, NY" /></label>
          <label>Official page<input type="url" name="officialUrl" required placeholder="https://…" /></label>
          <label>Waitlist page<input type="url" name="waitSourceUrl" required placeholder="https://…?party_size=4" /></label>
          <div className="form-pair">
            <label>Provider<input name="provider" defaultValue="Yelp Waitlist" required /></label>
            <label>Party sizes<input name="partySizes" defaultValue="4" required /></label>
          </div>
          <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save restaurant"}</button>
          {message ? <p className="form-message" role="status">{message}</p> : null}
        </form>
      </section>
    </main>
  );
}
