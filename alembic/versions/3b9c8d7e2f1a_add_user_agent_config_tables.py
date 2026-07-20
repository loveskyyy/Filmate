"""Add user_agent_config tables (v2)

Revision ID: 3b9c8d7e2f1a
Revises: d2f0c4a1b8e9
Create Date: 2026-07-02 10:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b9c8d7e2f1a"
down_revision: str | Sequence[str] | None = "d2f0c4a1b8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "user_agent_config" not in existing_tables:
        op.create_table(
            "user_agent_config",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=True),
            sa.Column("base_url", sa.Text(), nullable=True),
            sa.Column("api_key", sa.Text(), nullable=False),
            sa.Column("model", sa.String(length=128), nullable=True),
            sa.Column("embedding_model", sa.String(length=128), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("extra_config", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_agent_config_user_id", "user_agent_config", ["user_id"], unique=False)

    if "user_agent_preset" not in existing_tables:
        op.create_table(
            "user_agent_preset",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("model", sa.String(length=128), nullable=False),
            sa.Column("system_prompt", sa.Text(), nullable=True),
            sa.Column("config", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_agent_preset_user_id", "user_agent_preset", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "user_agent_preset" in existing_tables:
        op.drop_index("ix_user_agent_preset_user_id", table_name="user_agent_preset")
        op.drop_table("user_agent_preset")

    if "user_agent_config" in existing_tables:
        op.drop_index("ix_user_agent_config_user_id", table_name="user_agent_config")
        op.drop_table("user_agent_config")
