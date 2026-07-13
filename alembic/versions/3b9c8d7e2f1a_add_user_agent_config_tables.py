"""Add user_agent_config tables (v2)

Revision ID: 3b9c8d7e2f1a
Revises: a7a9749a1ae0
Create Date: 2026-07-02 10:50:00.000000

Note: Tables created manually via SQL, this migration just records the state.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "3b9c8d7e2f1a"
down_revision: str | Sequence[str] | None = "a7a9749a1ae0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Tables user_agent_config and user_agent_preset were created manually
    # This migration records that the schema is now at this version
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # Tables must be dropped manually if needed
    pass
