"""add is_admin to users

Revision ID: d071af46dc25
Revises: fc6425d9cc05
Create Date: 2026-08-03 13:31:39.823119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd071af46dc25'
down_revision: Union[str, Sequence[str], None] = 'fc6425d9cc05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))
    op.execute("UPDATE users SET is_admin = true WHERE username = 'admin'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_admin')
