CREATE TABLE circulation_documents (
 project_id TEXT NOT NULL REFERENCES projects(id), id TEXT NOT NULL,
 revision INTEGER NOT NULL, state TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(project_id,id)
);
CREATE TABLE circulation_history (
 project_id TEXT NOT NULL, document_id TEXT NOT NULL, revision INTEGER NOT NULL,
 state TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(project_id,document_id,revision)
);
CREATE TABLE circulation_corrections (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), document_id TEXT NOT NULL,
 region_id TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL, actor TEXT NOT NULL,
 created TEXT DEFAULT CURRENT_TIMESTAMP, training_example_id TEXT,
 UNIQUE(project_id,document_id,region_id,revision)
);
