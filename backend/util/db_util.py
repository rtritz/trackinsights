from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional


class Database:
    """Lightweight helper around the project SQLite database."""

    def __init__(self, db_path: str | Path):
        self.db_path = self._resolve_path(Path(db_path))
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}")

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        if path.is_absolute():
            return path

        project_root = Path(__file__).resolve().parents[2]
        candidate = project_root / path
        if candidate.exists():
            return candidate

        data_dir = project_root / "data"
        fallback = data_dir / path.name
        return fallback

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get_event_type(self, event_name: str) -> Optional[str]:
        query = "SELECT event_type FROM event WHERE event = ?"
        with self._connect() as conn:
            row = conn.execute(query, (event_name,)).fetchone()
            return row[0] if row else None

    def get_all_athlete_results(self) -> List[Dict[str, object]]:
        query = (
            """
            SELECT
                ar.athlete_id,
                ar.meet_id,
                ar.event,
                ar.result_type,
                ar.result,
                ar.result2,
                ar.place,
                m.meet_type,
                m.year,
                m.gender
            FROM athlete_result AS ar
            JOIN meet AS m ON ar.meet_id = m.meet_id
            """
        )
        with self._connect() as conn:
            cursor = conn.execute(query)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]
