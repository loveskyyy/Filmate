"""Alembic migration checks for agent_session_event_log ownership columns."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config()
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg.attributes["_test_db_path"] = str(db_path)
    return cfg


def _column_type(engine: sa.Engine, table_name: str, column_name: str) -> str:
    with engine.begin() as conn:
        rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    for row in rows:
        if row[1] == column_name:
            return str(row[2]).upper()
    raise AssertionError(f"{table_name}.{column_name} not found")


def test_event_log_user_id_matches_users_id_type(alembic_cfg: Config):
    command.upgrade(alembic_cfg, "f3d21ac90b17")

    db_path = alembic_cfg.attributes["_test_db_path"]
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        assert _column_type(engine, "users", "id").startswith("INTEGER")
        assert _column_type(engine, "agent_session_event_log", "user_id").startswith("INTEGER")
    finally:
        engine.dispose()
