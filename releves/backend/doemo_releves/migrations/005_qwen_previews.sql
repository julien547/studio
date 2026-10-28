CREATE TABLE qwen_previews (
 id TEXT PRIMARY KEY,
 version_id TEXT NOT NULL REFERENCES training_versions(id),
 example_id TEXT NOT NULL,
 baseline_job TEXT NOT NULL REFERENCES jobs(id),
 candidate_job TEXT NOT NULL REFERENCES jobs(id),
 author TEXT NOT NULL,
 request_key TEXT NOT NULL,
 request_sha256 TEXT NOT NULL,
 review TEXT,
 reviewer TEXT,
 reviewed TEXT,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(author,request_key)
);
CREATE INDEX qwen_previews_version ON qwen_previews(version_id,created);
