import { env } from "cloudflare:workers";
import { summarizeRecommendation } from "@/lib/recommendation";
import type {
  Observation,
  ObservationStatus,
  Restaurant,
  RestaurantDashboard,
} from "@/lib/types";

const DTF_SLUG = "din-tai-fung-new-york-3";
const DTF_WAIT_URL =
  "https://www.yelp.com/waitlist/din-tai-fung-new-york-3?party_size=4";

type RestaurantRow = {
  id: number;
  slug: string;
  name: string;
  city: string;
  address: string;
  timezone: string;
  official_url: string;
  wait_source_url: string;
  provider: string;
  party_sizes_json: string;
  interval_minutes: number;
  active: number;
  permission_reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

type ObservationRow = {
  id: number;
  restaurant_id: number;
  party_size: number;
  observed_at: string;
  status: ObservationStatus;
  wait_min_minutes: number | null;
  wait_max_minutes: number | null;
  wait_midpoint_minutes: number | null;
  raw_wait_text: string;
  source_url: string;
  source_provider: string;
  response_status_code: number | null;
  response_duration_ms: number | null;
  error_message: string | null;
  synthetic: number;
};

const schemaStatements = [
  `CREATE TABLE IF NOT EXISTS restaurants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    address TEXT NOT NULL,
    timezone TEXT NOT NULL,
    official_url TEXT NOT NULL,
    wait_source_url TEXT NOT NULL,
    provider TEXT NOT NULL,
    party_sizes_json TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL DEFAULT 15,
    active INTEGER NOT NULL DEFAULT 1,
    permission_reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    party_size INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    wait_min_minutes INTEGER,
    wait_max_minutes INTEGER,
    wait_midpoint_minutes REAL,
    raw_wait_text TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    source_provider TEXT NOT NULL,
    response_status_code INTEGER,
    response_duration_ms INTEGER,
    error_message TEXT,
    synthetic INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(restaurant_id, party_size, observed_at)
  )`,
  `CREATE INDEX IF NOT EXISTS observations_restaurant_party_time_idx
    ON observations(restaurant_id, party_size, observed_at)`,
  `CREATE TABLE IF NOT EXISTS actual_waits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    party_size INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    seated_at TEXT NOT NULL,
    actual_wait_minutes REAL NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS actual_waits_restaurant_party_idx
    ON actual_waits(restaurant_id, party_size)`,
];

function db(): D1Database {
  if (!env.DB) throw new Error("D1 binding DB is unavailable");
  return env.DB;
}

export async function initializeDatabase(): Promise<void> {
  const database = db();
  await database.batch(schemaStatements.map((statement) => database.prepare(statement)));
  const now = new Date().toISOString();
  await database
    .prepare(
      `INSERT OR IGNORE INTO restaurants (
        slug, name, city, address, timezone, official_url, wait_source_url,
        provider, party_sizes_json, interval_minutes, active,
        permission_reviewed_at, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)`,
    )
    .bind(
      DTF_SLUG,
      "Din Tai Fung",
      "New York, NY",
      "1633 Broadway, New York, NY 10019",
      "America/New_York",
      "https://www.yelp.com/biz/din-tai-fung-new-york-3?osq=Restaurants",
      DTF_WAIT_URL,
      "Yelp Waitlist",
      JSON.stringify([4]),
      15,
      now,
      now,
      now,
    )
    .run();
}

function restaurantFromRow(row: RestaurantRow): Restaurant {
  return {
    id: row.id,
    slug: row.slug,
    name: row.name,
    city: row.city,
    address: row.address,
    timezone: row.timezone,
    officialUrl: row.official_url,
    waitSourceUrl: row.wait_source_url,
    provider: row.provider,
    partySizes: JSON.parse(row.party_sizes_json) as number[],
    intervalMinutes: row.interval_minutes,
    active: row.active === 1,
    permissionReviewedAt: row.permission_reviewed_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function observationFromRow(row: ObservationRow): Observation {
  return {
    id: row.id,
    restaurantId: row.restaurant_id,
    partySize: row.party_size,
    observedAt: row.observed_at,
    status: row.status,
    waitMinMinutes: row.wait_min_minutes,
    waitMaxMinutes: row.wait_max_minutes,
    waitMidpointMinutes: row.wait_midpoint_minutes,
    rawWaitText: row.raw_wait_text,
    sourceUrl: row.source_url,
    sourceProvider: row.source_provider,
    responseStatusCode: row.response_status_code,
    responseDurationMs: row.response_duration_ms,
    errorMessage: row.error_message,
    synthetic: row.synthetic === 1,
  };
}

export async function getRestaurant(slug: string): Promise<Restaurant | null> {
  await initializeDatabase();
  const row = await db()
    .prepare("SELECT * FROM restaurants WHERE slug = ?")
    .bind(slug)
    .first<RestaurantRow>();
  return row ? restaurantFromRow(row) : null;
}

export async function listRestaurants(): Promise<Restaurant[]> {
  await initializeDatabase();
  const result = await db()
    .prepare("SELECT * FROM restaurants ORDER BY name")
    .all<RestaurantRow>();
  return (result.results ?? []).map(restaurantFromRow);
}

export async function listObservations(
  restaurantId: number,
  limit = 240,
): Promise<Observation[]> {
  const result = await db()
    .prepare(
      `SELECT * FROM observations WHERE restaurant_id = ?
       ORDER BY observed_at DESC LIMIT ?`,
    )
    .bind(restaurantId, limit)
    .all<ObservationRow>();
  return (result.results ?? []).map(observationFromRow).reverse();
}

export async function getLatestObservation(
  restaurantId: number,
  partySize: number,
): Promise<Observation | null> {
  const row = await db()
    .prepare(
      `SELECT * FROM observations WHERE restaurant_id = ? AND party_size = ?
       ORDER BY observed_at DESC LIMIT 1`,
    )
    .bind(restaurantId, partySize)
    .first<ObservationRow>();
  return row ? observationFromRow(row) : null;
}

export async function getRestaurantDashboard(
  slug: string,
): Promise<RestaurantDashboard | null> {
  const restaurant = await getRestaurant(slug);
  if (!restaurant) return null;
  const observations = await listObservations(restaurant.id);
  return {
    restaurant,
    observations,
    recommendation: summarizeRecommendation(observations),
  };
}

export type ObservationInput = Omit<Observation, "id" | "restaurantId">;

export async function insertObservation(
  restaurantId: number,
  input: ObservationInput,
): Promise<void> {
  await db()
    .prepare(
      `INSERT OR IGNORE INTO observations (
        restaurant_id, party_size, observed_at, status, wait_min_minutes,
        wait_max_minutes, wait_midpoint_minutes, raw_wait_text, source_url,
        source_provider, response_status_code, response_duration_ms,
        error_message, synthetic, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      restaurantId,
      input.partySize,
      input.observedAt,
      input.status,
      input.waitMinMinutes,
      input.waitMaxMinutes,
      input.waitMidpointMinutes,
      input.rawWaitText.slice(0, 2000),
      input.sourceUrl,
      input.sourceProvider,
      input.responseStatusCode,
      input.responseDurationMs,
      input.errorMessage,
      input.synthetic ? 1 : 0,
      new Date().toISOString(),
    )
    .run();
}

export async function upsertRestaurant(input: {
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
}): Promise<Restaurant> {
  await initializeDatabase();
  const now = new Date().toISOString();
  await db()
    .prepare(
      `INSERT INTO restaurants (
        slug, name, city, address, timezone, official_url, wait_source_url,
        provider, party_sizes_json, interval_minutes, active,
        permission_reviewed_at, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(slug) DO UPDATE SET
        name = excluded.name, city = excluded.city, address = excluded.address,
        timezone = excluded.timezone, official_url = excluded.official_url,
        wait_source_url = excluded.wait_source_url, provider = excluded.provider,
        party_sizes_json = excluded.party_sizes_json,
        interval_minutes = excluded.interval_minutes, active = excluded.active,
        permission_reviewed_at = excluded.permission_reviewed_at,
        updated_at = excluded.updated_at`,
    )
    .bind(
      input.slug,
      input.name,
      input.city,
      input.address,
      input.timezone,
      input.officialUrl,
      input.waitSourceUrl,
      input.provider,
      JSON.stringify(input.partySizes),
      input.intervalMinutes,
      input.active ? 1 : 0,
      input.permissionReviewedAt,
      now,
      now,
    )
    .run();
  const restaurant = await getRestaurant(input.slug);
  if (!restaurant) throw new Error("Restaurant was not saved");
  return restaurant;
}

export { DTF_SLUG };
