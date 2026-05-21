"""One-time database migration: add missing columns and tables."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'app.db')

if not os.path.exists(DB_PATH):
    print(f'DB not found at {DB_PATH}')
    exit(1)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Add missing columns to existing tables
migrations = [
    ("users", "is_active", "BOOLEAN DEFAULT 1"),
    ("users", "display_name", "VARCHAR(64)"),
    ("submissions", "file_size", "INTEGER"),
    ("submissions", "is_late", "BOOLEAN DEFAULT 0"),
    ("submissions", "version", "INTEGER DEFAULT 1"),
    ("submissions", "ast_data", "JSON"),
]

for table, col, dtype in migrations:
    try:
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {dtype}')
        print(f'+ Added {table}.{col}')
    except sqlite3.OperationalError:
        print(f'- {table}.{col} already exists')

# Create missing tables
cur.execute('''CREATE TABLE IF NOT EXISTS submission_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES submissions(id),
    file_path VARCHAR(512) NOT NULL,
    file_name VARCHAR(256) NOT NULL,
    uploaded_at DATETIME
)''')
print('* submission_versions table ready')

cur.execute('''CREATE TABLE IF NOT EXISTS code_fragments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    similarity_result_id INTEGER NOT NULL REFERENCES similarity_results(id),
    source_start_line INTEGER,
    source_end_line INTEGER,
    target_start_line INTEGER,
    target_end_line INTEGER,
    similarity FLOAT
)''')
print('* code_fragments table ready')

cur.execute('''CREATE TABLE IF NOT EXISTS system_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key VARCHAR(64) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    description VARCHAR(256),
    updated_at DATETIME,
    updated_by INTEGER REFERENCES users(id)
)''')
print('* system_config table ready')

conn.commit()
conn.close()
print('Migration complete!')
