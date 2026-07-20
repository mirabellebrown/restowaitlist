CREATE TABLE `actual_waits` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`restaurant_id` integer NOT NULL,
	`party_size` integer NOT NULL,
	`joined_at` text NOT NULL,
	`seated_at` text NOT NULL,
	`actual_wait_minutes` real NOT NULL,
	`notes` text DEFAULT '' NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`restaurant_id`) REFERENCES `restaurants`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `actual_waits_restaurant_party_idx` ON `actual_waits` (`restaurant_id`,`party_size`);--> statement-breakpoint
CREATE TABLE `observations` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`restaurant_id` integer NOT NULL,
	`party_size` integer NOT NULL,
	`observed_at` text NOT NULL,
	`status` text NOT NULL,
	`wait_min_minutes` integer,
	`wait_max_minutes` integer,
	`wait_midpoint_minutes` real,
	`raw_wait_text` text DEFAULT '' NOT NULL,
	`source_url` text NOT NULL,
	`source_provider` text NOT NULL,
	`response_status_code` integer,
	`response_duration_ms` integer,
	`error_message` text,
	`synthetic` integer DEFAULT false NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`restaurant_id`) REFERENCES `restaurants`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `observations_restaurant_party_time_idx` ON `observations` (`restaurant_id`,`party_size`,`observed_at`);--> statement-breakpoint
CREATE UNIQUE INDEX `observations_source_event_uq` ON `observations` (`restaurant_id`,`party_size`,`observed_at`);--> statement-breakpoint
CREATE TABLE `restaurants` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`slug` text NOT NULL,
	`name` text NOT NULL,
	`city` text NOT NULL,
	`address` text NOT NULL,
	`timezone` text NOT NULL,
	`official_url` text NOT NULL,
	`wait_source_url` text NOT NULL,
	`provider` text NOT NULL,
	`party_sizes_json` text NOT NULL,
	`interval_minutes` integer DEFAULT 15 NOT NULL,
	`active` integer DEFAULT true NOT NULL,
	`permission_reviewed_at` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `restaurants_slug_uq` ON `restaurants` (`slug`);