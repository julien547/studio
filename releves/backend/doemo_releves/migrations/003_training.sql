CREATE TABLE training_categories (
 code TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1
);
INSERT INTO training_categories VALUES
 ('WALL','Murs','wall',1),('DOOR','Portes','door',1),('OPENING','Ouvertures','opening',1),
 ('FIRE','Équipements incendie','equipment',1),('HANDWRITING','Annotations manuscrites','text',1),
 ('OTHER','Autres','other',1);
CREATE TABLE training_examples (
 id TEXT PRIMARY KEY, engine TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
 document_id TEXT NOT NULL REFERENCES documents(id), page INTEGER NOT NULL, revision INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','validated','rejected')),
 data TEXT NOT NULL, author TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX training_examples_filter ON training_examples(engine,project_id,status);
CREATE TABLE training_revisions (
 example_id TEXT NOT NULL REFERENCES training_examples(id), revision INTEGER NOT NULL,
 status TEXT NOT NULL, data TEXT NOT NULL, actor TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(example_id,revision)
);
CREATE TABLE training_datasets (
 id TEXT PRIMARY KEY, engine TEXT NOT NULL, name TEXT NOT NULL, version INTEGER NOT NULL,
 snapshot TEXT NOT NULL, sha256 TEXT NOT NULL, author TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(engine,name,version)
);
CREATE TABLE training_runs (
 id TEXT PRIMARY KEY, engine TEXT NOT NULL, dataset_id TEXT NOT NULL REFERENCES training_datasets(id),
 parameters TEXT NOT NULL, status TEXT NOT NULL, progress REAL, result TEXT, error TEXT,
 author TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE training_versions (
 id TEXT PRIMARY KEY, engine TEXT NOT NULL, name TEXT NOT NULL, method TEXT NOT NULL,
 dataset_id TEXT NOT NULL REFERENCES training_datasets(id), run_id TEXT REFERENCES training_runs(id),
 status TEXT NOT NULL CHECK(status IN ('development','candidate','approved','production','archived')),
 manifest TEXT NOT NULL, evaluation TEXT, author TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE training_deployments (
 engine TEXT PRIMARY KEY, version_id TEXT REFERENCES training_versions(id), previous_id TEXT REFERENCES training_versions(id),
 generation INTEGER NOT NULL DEFAULT 0
);
INSERT INTO training_deployments(engine) VALUES('qwen'),('paddleocr'),('rtmdet'),('architecture');
CREATE TABLE training_audit (
 id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, entity TEXT NOT NULL,
 detail TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
