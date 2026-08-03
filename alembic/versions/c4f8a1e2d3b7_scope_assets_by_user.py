"""scope assets by user

Revision ID: c4f8a1e2d3b7
Revises: a2b3c4d5e6f7
Create Date: 2026-08-03 14:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4f8a1e2d3b7"
down_revision: str | Sequence[str] | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("assets", schema=None) as batch_op:
        batch_op.drop_constraint("uq_asset_type_name", type_="unique")
        batch_op.add_column(sa.Column("user_id", sa.Integer(), server_default="1", nullable=False))
        batch_op.create_foreign_key("fk_assets_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE")
        batch_op.create_index("ix_assets_user_id", ["user_id"], unique=False)
        batch_op.create_index("ix_asset_user_type", ["user_id", "type"], unique=False)
        batch_op.create_unique_constraint("uq_asset_user_type_name", ["user_id", "type", "name"])


def downgrade() -> None:
    with op.batch_alter_table("assets", schema=None) as batch_op:
        batch_op.drop_constraint("uq_asset_user_type_name", type_="unique")
        batch_op.drop_index("ix_asset_user_type")
        batch_op.drop_index("ix_assets_user_id")
        batch_op.drop_constraint("fk_assets_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
        batch_op.create_unique_constraint("uq_asset_type_name", ["type", "name"])
