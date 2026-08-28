import json
from typing import Optional, List, Dict, Any
from app.database import db

class RepositoryModel:

    @classmethod
    def get_all(cls) -> List[Dict[str, Any]]:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repositories ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [cls._deserialize(dict(row)) for row in rows]

    @classmethod
    def get_by_id(cls, repo_id: str) -> Optional[Dict[str, Any]]:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repositories WHERE repo_id = ?", (repo_id,))
            row = cursor.fetchone()
            return cls._deserialize(dict(row)) if row else None

    @classmethod
    def upsert(cls, repo_id: str, repo_name: str, owner: str, source_type: str, source_url: str):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO repositories (repo_id, repo_name, owner, source_type, source_url)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(repo_id) DO UPDATE SET
                    repo_name = excluded.repo_name,
                    owner = excluded.owner,
                    source_type = excluded.source_type,
                    source_url = excluded.source_url
            """, (repo_id, repo_name, owner, source_type, source_url))
            conn.commit()

    @classmethod
    def update_counts(cls, repo_id: str, chunk_count: int, vector_count: int):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE repositories
                SET chunk_count = ?, vector_count = ?
                WHERE repo_id = ?
            """, (chunk_count, vector_count, repo_id))
            conn.commit()

    @classmethod
    def update_quality_score(cls, repo_id: str, score: int) -> None:
        """Persists the overall engineering quality score."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE repositories SET quality_score = ? WHERE repo_id = ?",
                (score, repo_id)
            )
            conn.commit()

    @classmethod
    def update_manifest(cls, repo_id: str, manifest: Dict[str, Any]) -> None:
        """Persists the repository manifest as a JSON blob and updates language/framework columns."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE repositories
                SET manifest = ?, languages = ?, frameworks = ?, repo_name = ?, owner = ?
                WHERE repo_id = ?
            """, (
                json.dumps(manifest),
                json.dumps(manifest.get("languages", [])),
                json.dumps(manifest.get("frameworks", [])),
                manifest.get("repo_name", repo_id),
                manifest.get("owner", "local"),
                repo_id,
            ))
            conn.commit()

    @classmethod
    def delete(cls, repo_id: str):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM repositories WHERE repo_id = ?", (repo_id,))
            conn.commit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _deserialize(row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses JSON-serialized columns back into Python objects.
        """
        for key in ("languages", "frameworks", "manifest"):
            val = row.get(key)
            if isinstance(val, str) and val:
                try:
                    row[key] = json.loads(val)
                except Exception:
                    row[key] = {} if key == "manifest" else []
            elif val is None:
                row[key] = {} if key == "manifest" else []
        return row
