ALTER TABLE projects ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}';
CREATE TABLE revisions (
 project_id TEXT NOT NULL REFERENCES projects(id), revision INTEGER NOT NULL,
 actor TEXT NOT NULL, state TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(project_id,revision)
);
CREATE TABLE users (
 login TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','administration','dessinateur')),
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE sessions (
 token_hash TEXT PRIMARY KEY, login TEXT NOT NULL REFERENCES users(login), expires REAL NOT NULL
);
CREATE TABLE login_attempts (key TEXT PRIMARY KEY, failures INTEGER NOT NULL, reset_at REAL NOT NULL);
CREATE TABLE jobs (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), actor TEXT NOT NULL,
 status TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL, result TEXT,
 error TEXT, attempts INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP,
 updated TEXT DEFAULT CURRENT_TIMESTAMP, lease_until REAL
);
CREATE INDEX jobs_pending ON jobs(status,created);
CREATE TABLE equipment_catalogue (code TEXT PRIMARY KEY, data TEXT NOT NULL);
INSERT INTO revisions(project_id,revision,actor,state) SELECT id,revision,owner,state FROM projects;
