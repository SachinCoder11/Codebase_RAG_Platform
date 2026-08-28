import sqlite3
from typing import Optional
from pathlib import Path
from app.core.config import settings

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        self.db_path = settings.BASE_DATA_DIR / "registry.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()
        self._migrate_tables()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    repo_id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    owner TEXT,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    chunk_count INTEGER DEFAULT 0,
                    vector_count INTEGER DEFAULT 0,
                    quality_score INTEGER DEFAULT 0,
                    languages TEXT DEFAULT '{}',
                    frameworks TEXT DEFAULT '[]',
                    manifest TEXT DEFAULT '{}'
                )
            """)
            conn.commit()

    def _migrate_tables(self):
        """
        Non-destructive migration: adds new columns to existing databases
        that were created before Phase 3.
        """
        new_columns = [
            ("quality_score", "INTEGER DEFAULT 0"),
            ("languages",     "TEXT DEFAULT '{}'"),
            ("frameworks",    "TEXT DEFAULT '[]'"),
            ("manifest",      "TEXT DEFAULT '{}'"),
        ]
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Get existing columns
            cursor.execute("PRAGMA table_info(repositories)")
            existing = {row["name"] for row in cursor.fetchall()}
            for col_name, col_def in new_columns:
                if col_name not in existing:
                    cursor.execute(
                        f"ALTER TABLE repositories ADD COLUMN {col_name} {col_def}"
                    )
            conn.commit()

db = Database()
