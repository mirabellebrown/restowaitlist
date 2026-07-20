SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    timezone TEXT NOT NULL,
    official_url TEXT NOT NULL,
    wait_source_url TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(name, wait_source_url)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    started_at_utc TEXT NOT NULL,
    scheduled_end_at_utc TEXT NOT NULL,
    actual_end_at_utc TEXT,
    interval_minutes INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('running', 'completed', 'stopped')),
    source_type TEXT NOT NULL,
    app_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES collection_runs(id),
    location_id INTEGER NOT NULL REFERENCES locations(id),
    party_size INTEGER NOT NULL,
    scheduled_at_utc TEXT NOT NULL,
    observed_at_utc TEXT,
    observed_at_local TEXT,
    status TEXT NOT NULL,
    wait_min_minutes INTEGER,
    wait_max_minutes INTEGER,
    wait_midpoint_minutes REAL,
    wait_is_open_ended INTEGER NOT NULL DEFAULT 0,
    parties_ahead INTEGER,
    raw_wait_text TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    source_provider TEXT NOT NULL DEFAULT '',
    parser_name TEXT NOT NULL DEFAULT '',
    response_status_code INTEGER,
    response_duration_ms INTEGER,
    content_hash TEXT,
    error_message TEXT,
    created_at_utc TEXT NOT NULL,
    UNIQUE(run_id, location_id, party_size, scheduled_at_utc)
);

CREATE INDEX IF NOT EXISTS ix_observations_location_party_time
ON observations(location_id, party_size, scheduled_at_utc);

CREATE TABLE IF NOT EXISTS actual_waits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    party_size INTEGER NOT NULL,
    joined_at_utc TEXT NOT NULL,
    seated_at_utc TEXT NOT NULL,
    actual_wait_minutes REAL NOT NULL,
    displayed_wait_min_minutes INTEGER,
    displayed_wait_max_minutes INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL
);
"""
