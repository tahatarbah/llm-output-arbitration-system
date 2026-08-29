"""SQLite persistence for arbitration runs."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from llm_arbitration.models import ArbitrateResult, RunSummary


def _default_db_path() -> Path:
    root = Path.cwd() / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root / "arbitration.db"


def resolve_db_path(database_url: str | None = None) -> Path:
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/arbitration.db")
    if url.startswith("sqlite:///"):
        raw = url[len("sqlite:///") :]
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    parsed = urlparse(url)
    if parsed.scheme in ("", "sqlite"):
        path = Path(parsed.path or "./data/arbitration.db")
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    # Fallback: treat as filesystem path
    path = Path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class RunStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.path = resolve_db_path(database_url)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    arbiter_model TEXT NOT NULL,
                    generator_models TEXT NOT NULL,
                    final_answer TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC)"
            )
            conn.commit()

    def save(self, result: ArbitrateResult) -> None:
        payload = result.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs
                (run_id, created_at, prompt, arbiter_model, generator_models, final_answer, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    result.created_at.isoformat(),
                    result.prompt,
                    result.arbiter_model,
                    json.dumps(result.generator_models),
                    result.final_answer,
                    json.dumps(payload),
                ),
            )
            conn.commit()

    def get(self, run_id: str) -> ArbitrateResult | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        data: dict[str, Any] = json.loads(row["payload"])
        return ArbitrateResult.model_validate(data)

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[RunSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, prompt, arbiter_model, generator_models, created_at, final_answer
                FROM runs
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        summaries: list[RunSummary] = []
        for row in rows:
            preview = row["final_answer"] or ""
            if len(preview) > 160:
                preview = preview[:157] + "..."
            created_raw = row["created_at"]
            created_at = (
                datetime.fromisoformat(created_raw)
                if isinstance(created_raw, str)
                else created_raw
            )
            summaries.append(
                RunSummary(
                    run_id=row["run_id"],
                    prompt=row["prompt"],
                    arbiter_model=row["arbiter_model"],
                    generator_models=json.loads(row["generator_models"]),
                    created_at=created_at,
                    final_answer_preview=preview,
                )
            )
        return summaries
