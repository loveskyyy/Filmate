"""add users.email, hashed_password, credits columns

Revision ID: a2b3c4d5e6f7
Revises: f1a2c4d5e6f7
Create Date: 2026-07-29 16:00:00.000000

ea2e1a477bbf 创建 users 表时只建了 (id, username, role, is_active,
created_at, updated_at) 这 6 个字段。后续迁移没有补 email /
hashed_password / credits,但 lib/db/models/user.py 当前模型需要这三个字段。
SELECT User.* 会触发 SQLAlchemy 生成包含这些列的 SQL,SQLite 报
"no such column" 导致 /api/v1/auth/register 等接口 500。

本迁移把缺的 3 列补上,idempotent 跳过已存在的列(对老库无害)。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TARGET_TABLE = "users"


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if table_name not in sa.inspect(bind).get_table_names():
        return False
    return any(col["name"] == column_name for col in sa.inspect(bind).get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if _TARGET_TABLE not in sa.inspect(bind).get_table_names():
        return

    with op.batch_alter_table(_TARGET_TABLE, schema=None) as batch_op:
        if not _column_exists(bind, _TARGET_TABLE, "email"):
            batch_op.add_column(sa.Column("email", sa.String(), nullable=True))
            batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        if not _column_exists(bind, _TARGET_TABLE, "hashed_password"):
            batch_op.add_column(sa.Column("hashed_password", sa.String(), nullable=True))
        if not _column_exists(bind, _TARGET_TABLE, "credits"):
            batch_op.add_column(
                sa.Column(
                    "credits",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    if _TARGET_TABLE not in sa.inspect(bind).get_table_names():
        return
    with op.batch_alter_table(_TARGET_TABLE, schema=None) as batch_op:
        if _column_exists(bind, _TARGET_TABLE, "email"):
            try:
                batch_op.drop_index(batch_op.f("ix_users_email"))
            except Exception:
                pass  # 索引可能不存在
            batch_op.drop_column("email")
        if _column_exists(bind, _TARGET_TABLE, "hashed_password"):
            batch_op.drop_column("hashed_password")
        if _column_exists(bind, _TARGET_TABLE, "credits"):
            batch_op.drop_column("credits")
