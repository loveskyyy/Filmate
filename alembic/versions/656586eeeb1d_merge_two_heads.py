"""merge two heads

Revision ID: 656586eeeb1d
Revises: 5d879328dd53, bd25b66f82e8
Create Date: 2026-07-13 16:47:36.591588

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "656586eeeb1d"
down_revision: str | Sequence[str] | None = ("5d879328dd53", "bd25b66f82e8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
