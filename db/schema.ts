import { index, integer, real, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const restaurants = sqliteTable(
  "restaurants",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    slug: text("slug").notNull(),
    name: text("name").notNull(),
    city: text("city").notNull(),
    address: text("address").notNull(),
    timezone: text("timezone").notNull(),
    officialUrl: text("official_url").notNull(),
    waitSourceUrl: text("wait_source_url").notNull(),
    provider: text("provider").notNull(),
    partySizesJson: text("party_sizes_json").notNull(),
    intervalMinutes: integer("interval_minutes").notNull().default(15),
    active: integer("active", { mode: "boolean" }).notNull().default(true),
    permissionReviewedAt: text("permission_reviewed_at"),
    createdAt: text("created_at").notNull(),
    updatedAt: text("updated_at").notNull(),
  },
  (table) => [uniqueIndex("restaurants_slug_uq").on(table.slug)],
);

export const observations = sqliteTable(
  "observations",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    restaurantId: integer("restaurant_id")
      .notNull()
      .references(() => restaurants.id, { onDelete: "cascade" }),
    partySize: integer("party_size").notNull(),
    observedAt: text("observed_at").notNull(),
    status: text("status").notNull(),
    waitMinMinutes: integer("wait_min_minutes"),
    waitMaxMinutes: integer("wait_max_minutes"),
    waitMidpointMinutes: real("wait_midpoint_minutes"),
    rawWaitText: text("raw_wait_text").notNull().default(""),
    sourceUrl: text("source_url").notNull(),
    sourceProvider: text("source_provider").notNull(),
    responseStatusCode: integer("response_status_code"),
    responseDurationMs: integer("response_duration_ms"),
    errorMessage: text("error_message"),
    synthetic: integer("synthetic", { mode: "boolean" }).notNull().default(false),
    createdAt: text("created_at").notNull(),
  },
  (table) => [
    index("observations_restaurant_party_time_idx").on(
      table.restaurantId,
      table.partySize,
      table.observedAt,
    ),
    uniqueIndex("observations_source_event_uq").on(
      table.restaurantId,
      table.partySize,
      table.observedAt,
    ),
  ],
);

export const actualWaits = sqliteTable(
  "actual_waits",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    restaurantId: integer("restaurant_id")
      .notNull()
      .references(() => restaurants.id, { onDelete: "cascade" }),
    partySize: integer("party_size").notNull(),
    joinedAt: text("joined_at").notNull(),
    seatedAt: text("seated_at").notNull(),
    actualWaitMinutes: real("actual_wait_minutes").notNull(),
    notes: text("notes").notNull().default(""),
    createdAt: text("created_at").notNull(),
  },
  (table) => [index("actual_waits_restaurant_party_idx").on(table.restaurantId, table.partySize)],
);
