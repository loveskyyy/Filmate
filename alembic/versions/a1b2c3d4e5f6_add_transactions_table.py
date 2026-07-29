"""add transactions table

Revision ID: a1b2c3d4e5f6
Revises: 656586eeeb1d
Create Date: 2026-07-24 09:30:00.000000

积分交易表,与 User.credits (int) 配套,记录每次积分变动作为审计/对账的真相源。
amount / credits_before / credits_after 全部用 Integer;trade_no 唯一索引,
与微信商户订单号对齐。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "656586eeeb1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("credits_before", sa.Integer(), nullable=False),
        sa.Column("credits_after", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("trade_no", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("extra", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"], unique=False)
    # trade_no 唯一索引:微信回调幂等性 + 防止重复写
    op.create_index("ix_transactions_trade_no", "transactions", ["trade_no"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_transactions_trade_no", table_name="transactions")
    op.drop_index("ix_transactions_user_id", table_name="transactions")
    op.drop_table("transactions")
