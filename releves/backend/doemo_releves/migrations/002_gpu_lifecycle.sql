CREATE TABLE gpu_control (
 id INTEGER PRIMARY KEY CHECK(id=1), phase TEXT NOT NULL DEFAULT 'not_configured',
 provider_status TEXT, pod_id TEXT, gateway_url TEXT, boot_id TEXT,
 request TEXT, requested_by TEXT, pending_action TEXT, action_at REAL,
 next_poll REAL NOT NULL DEFAULT 0, last_activity REAL NOT NULL DEFAULT 0,
 observed_at REAL, failures INTEGER NOT NULL DEFAULT 0, error TEXT,
 engines TEXT NOT NULL DEFAULT '{}', quiesced INTEGER NOT NULL DEFAULT 0
);
INSERT INTO gpu_control(id) VALUES(1);
CREATE TABLE gpu_events (
 id INTEGER PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
 actor TEXT NOT NULL, action TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}'
);
ALTER TABLE jobs ADD COLUMN retry_at REAL NOT NULL DEFAULT 0;
CREATE INDEX jobs_gpu_pending ON jobs(status,retry_at);
