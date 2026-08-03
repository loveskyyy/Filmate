"""Tests for BaseRepository and _scope_query mechanism."""

from unittest.mock import MagicMock

from sqlalchemy import select

from lib.db.models import Task
from lib.db.repositories.base import BaseRepository


class TestBaseRepository:
    def test_scope_query_noop(self):
        """_scope_query returns stmt unchanged by default."""
        repo = BaseRepository(MagicMock())
        stmt = select(Task)
        result = repo._scope_query(stmt, Task)
        assert str(result) == str(stmt)

    def test_scope_query_filters_user_owned_model(self):
        repo = BaseRepository(MagicMock(), user_id=7)
        result = repo._scope_query(select(Task), Task)
        assert "user_id" in str(result)

    def test_scope_query_overridable(self):
        """Subclass can override _scope_query to add filters."""

        class ScopedRepo(BaseRepository):
            def _scope_query(self, stmt, model):
                return stmt.where(model.user_id == "test-user")

        repo = ScopedRepo.__new__(ScopedRepo)
        stmt = select(Task)
        result = repo._scope_query(stmt, Task)
        assert "user_id" in str(result)
