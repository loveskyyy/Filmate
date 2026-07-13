"""Alter user_agent_config to match custom_provider schema

Revision ID: 5d879328dd53
Revises: 3b9c8d7e2f1a
Create Date: 2026-07-03 11:13:20.285268

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d879328dd53"
down_revision: str | Sequence[str] | None = "3b9c8d7e2f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("user_agent_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("discovery_format", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("image_max_workers", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("video_max_workers", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("audio_max_workers", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("price_unit", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("price_input", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("price_output", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("currency", sa.String(length=8), nullable=True))

    # 根据 provider 列的值迁移数据到 discovery_format
    op.execute(
        "UPDATE user_agent_config SET discovery_format = 'openai' WHERE provider IN ('openai', 'anthropic', 'custom', 'dashscope', 'volcengine') OR provider IS NULL"
    )
    op.execute("UPDATE user_agent_config SET discovery_format = 'google' WHERE provider = 'google'")

    # 删掉 provider 列，discovery_format 改为 NOT NULL，创建新索引
    with op.batch_alter_table("user_agent_config", schema=None) as batch_op:
        batch_op.drop_column("provider")
        batch_op.alter_column("discovery_format", existing_type=sa.String(length=32), nullable=False)
        batch_op.create_index("ix_user_agent_config_user_discovery", ["user_id", "discovery_format"], unique=False)
        batch_op.alter_column("base_url", existing_type=sa.TEXT(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_agent_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider", sa.VARCHAR(length=64), autoincrement=False, nullable=False))
        batch_op.drop_index("ix_user_agent_config_user_discovery")
        batch_op.alter_column("base_url", existing_type=sa.TEXT(), nullable=True)
        batch_op.drop_column("currency")
        batch_op.drop_column("price_output")
        batch_op.drop_column("price_input")
        batch_op.drop_column("price_unit")
        batch_op.drop_column("audio_max_workers")
        batch_op.drop_column("video_max_workers")
        batch_op.drop_column("image_max_workers")
        batch_op.drop_column("discovery_format")
