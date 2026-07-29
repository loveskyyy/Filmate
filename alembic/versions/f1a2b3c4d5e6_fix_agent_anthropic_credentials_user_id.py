"""fix agent_anthropic_credentials.user_id to integer

Revision ID: f1a2b3c4d5e6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-24 15:00:00.000000

d2f0c4a1b8e9_convert_user_ids_to_int 迁移在跑的时候,agent_anthropic_credentials
表的 user_id 列没被实际 ALTER(可能因当时表不存在 / 默认值 / 校验失败等,
alembic schema_version 仍 mark 该迁移为已应用)。结果:_USER_ID_TABLES 列表
中只有这一张表的 user_id 仍是 character varying,运行时 PostgreSQL 抛
"operator does not exist: character varying = integer"。

本迁移只针对 agent_anthropic_credentials.user_id 兜底修复,与之前的
d2f0c4a1b8e9 行为保持一致(drop FK → ALTER COLUMN TYPE → recreate FK),
避免触碰已经正确的其他表。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TARGET_TABLE = "agent_anthropic_credentials"
_TARGET_COLUMN = "user_id"


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _column_is_integer(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    for col in sa.inspect(bind).get_columns(table_name):
        if col["name"] == column_name:
            return isinstance(col["type"], sa.Integer)
    return False


def _user_fks_to_drop(bind) -> list[str]:
    """返回指向 users 表的 FK 名称列表(用于先 drop、再 recreate)。"""
    if not _table_exists(bind, _TARGET_TABLE):
        return []
    fk_names: list[str] = []
    for fk in sa.inspect(bind).get_foreign_keys(_TARGET_TABLE):
        if fk.get("referred_table") != "users":
            continue
        name = fk.get("name")
        if not name:
            continue
        cols = list(fk.get("constrained_columns") or [])
        if _TARGET_COLUMN in cols:
            fk_names.append(name)
    return fk_names


def _validate_text_user_id(bind) -> None:
    """与 d2f0c4a1b8e9 一致:仅允许纯数字或 'default',否则 raise。"""
    invalid_count = bind.execute(
        sa.text(
            f"""
            SELECT count(*)
            FROM {_q(_TARGET_TABLE)}
            WHERE {_q(_TARGET_COLUMN)} IS NOT NULL
              AND {_q(_TARGET_COLUMN)} <> 'default'
              AND {_q(_TARGET_COLUMN)} !~ '^[0-9]+$'
            """
        )
    ).scalar_one()
    if invalid_count:
        raise RuntimeError(
            f"{_TARGET_TABLE}.{_TARGET_COLUMN} contains {invalid_count} non-numeric user ids; "
            "convert them before running this migration"
        )


def _to_int_expr() -> str:
    return f"CASE WHEN {_q(_TARGET_COLUMN)} = 'default' THEN 1 ELSE {_q(_TARGET_COLUMN)}::integer END"


def _to_text_expr() -> str:
    return f"CASE WHEN {_q(_TARGET_COLUMN)} = 1 THEN 'default' ELSE {_q(_TARGET_COLUMN)}::text END"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _table_exists(bind, _TARGET_TABLE):
        return
    # 已经是 integer(其他环境已修过),幂等跳过
    if _column_is_integer(bind, _TARGET_TABLE, _TARGET_COLUMN):
        return

    _validate_text_user_id(bind)

    fk_names = _user_fks_to_drop(bind)
    for fk_name in fk_names:
        op.drop_constraint(fk_name, _TARGET_TABLE, type_="foreignkey")

    table = _q(_TARGET_TABLE)
    column = _q(_TARGET_COLUMN)
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE integer USING {_to_int_expr()}"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT 1"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"))

    for fk_name in fk_names:
        op.create_foreign_key(fk_name, _TARGET_TABLE, "users", [_TARGET_COLUMN], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _table_exists(bind, _TARGET_TABLE):
        return
    if not _column_is_integer(bind, _TARGET_TABLE, _TARGET_COLUMN):
        return  # 当前是 varchar,无需降级

    fk_names = _user_fks_to_drop(bind)
    for fk_name in fk_names:
        op.drop_constraint(fk_name, _TARGET_TABLE, type_="foreignkey")

    table = _q(_TARGET_TABLE)
    column = _q(_TARGET_COLUMN)
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar USING {_to_text_expr()}"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT 'default'"))
    op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"))

    for fk_name in fk_names:
        op.create_foreign_key(fk_name, _TARGET_TABLE, "users", [_TARGET_COLUMN], ["id"], ondelete="CASCADE")
