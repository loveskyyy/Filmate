"""convert user ids to integer

Revision ID: d2f0c4a1b8e9
Revises: a7a9749a1ae0
Create Date: 2026-07-20 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2f0c4a1b8e9"
down_revision: str | Sequence[str] | None = "a7a9749a1ae0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_ID_TABLES = (
    "tasks",
    "api_calls",
    "api_keys",
    "agent_sessions",
    "agent_session_entries",
    "agent_session_summaries",
    "agent_anthropic_credentials",
    "agent_session_event_log",
    "user_agent_config",
    "user_agent_preset",
)


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return any(col["name"] == column_name for col in sa.inspect(bind).get_columns(table_name))


def _column_is_integer(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    for col in sa.inspect(bind).get_columns(table_name):
        if col["name"] == column_name:
            return isinstance(col["type"], sa.Integer)
    return False


def _user_fks(bind) -> list[tuple[str, str, list[str]]]:
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    fks: list[tuple[str, str, list[str]]] = []
    for table_name in _USER_ID_TABLES:
        if table_name not in existing_tables:
            continue
        for fk in inspector.get_foreign_keys(table_name):
            if fk.get("referred_table") != "users":
                continue
            name = fk.get("name")
            constrained_columns = list(fk.get("constrained_columns") or [])
            if name and constrained_columns:
                fks.append((table_name, name, constrained_columns))
    return fks


def _validate_text_user_id(bind, table_name: str, column_name: str) -> None:
    invalid_count = bind.execute(
        sa.text(
            f"""
            SELECT count(*)
            FROM {_q(table_name)}
            WHERE {_q(column_name)} IS NOT NULL
              AND {_q(column_name)} <> 'default'
              AND {_q(column_name)} !~ '^[0-9]+$'
            """
        )
    ).scalar_one()
    if invalid_count:
        raise RuntimeError(
            f"{table_name}.{column_name} contains non-numeric user ids; convert them before running this migration"
        )


def _to_int_expr(column_name: str) -> str:
    column = _q(column_name)
    return f"CASE WHEN {column} = 'default' THEN 1 ELSE {column}::integer END"


def _to_text_expr(column_name: str) -> str:
    column = _q(column_name)
    return f"CASE WHEN {column} = 1 THEN 'default' ELSE {column}::text END"


def _convert_column_to_int(bind, table_name: str, column_name: str) -> None:
    if not _column_exists(bind, table_name, column_name) or _column_is_integer(bind, table_name, column_name):
        return
    _validate_text_user_id(bind, table_name, column_name)
    table = _q(table_name)
    column = _q(column_name)
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE integer USING {_to_int_expr(column_name)}"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT 1"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"))


def _convert_column_to_text(bind, table_name: str, column_name: str) -> None:
    if not _column_exists(bind, table_name, column_name) or not _column_is_integer(bind, table_name, column_name):
        return
    table = _q(table_name)
    column = _q(column_name)
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar USING {_to_text_expr(column_name)}"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT 'default'"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"))


def _drop_fks(fks: list[tuple[str, str, list[str]]]) -> None:
    for table_name, fk_name, _columns in fks:
        op.drop_constraint(fk_name, table_name, type_="foreignkey")


def _recreate_fks(fks: list[tuple[str, str, list[str]]]) -> None:
    for table_name, fk_name, columns in fks:
        op.create_foreign_key(fk_name, table_name, "users", columns, ["id"], ondelete="CASCADE")


def _upgrade_postgresql(bind) -> None:
    if not _table_exists(bind, "users") or _column_is_integer(bind, "users", "id"):
        return

    fks = _user_fks(bind)
    _drop_fks(fks)
    for table_name in _USER_ID_TABLES:
        _convert_column_to_int(bind, table_name, "user_id")

    _validate_text_user_id(bind, "users", "id")
    op.execute(sa.text('ALTER TABLE "users" ALTER COLUMN "id" DROP DEFAULT'))
    op.execute(sa.text(f'ALTER TABLE "users" ALTER COLUMN "id" TYPE integer USING {_to_int_expr("id")}'))
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS users_id_seq OWNED BY users.id"))
    op.execute(sa.text("SELECT setval('users_id_seq', GREATEST(COALESCE((SELECT max(id) FROM users), 1), 1))"))
    op.execute(sa.text("ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq')"))
    op.execute(sa.text('ALTER TABLE "users" ALTER COLUMN "id" SET NOT NULL'))
    _recreate_fks(fks)


def _downgrade_postgresql(bind) -> None:
    if not _table_exists(bind, "users") or not _column_is_integer(bind, "users", "id"):
        return

    fks = _user_fks(bind)
    _drop_fks(fks)
    for table_name in _USER_ID_TABLES:
        _convert_column_to_text(bind, table_name, "user_id")

    op.execute(sa.text('ALTER TABLE "users" ALTER COLUMN "id" DROP DEFAULT'))
    op.execute(sa.text(f'ALTER TABLE "users" ALTER COLUMN "id" TYPE varchar USING {_to_text_expr("id")}'))
    op.execute(sa.text("DROP SEQUENCE IF EXISTS users_id_seq"))
    op.execute(sa.text('ALTER TABLE "users" ALTER COLUMN "id" SET NOT NULL'))
    _recreate_fks(fks)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _upgrade_postgresql(bind)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _downgrade_postgresql(bind)
