"""add document review status

Revision ID: 1f83d3e98af8
Revises: 4bffcba11b73
Create Date: 2026-07-14 17:42:38.504320

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f83d3e98af8'
down_revision: Union[str, Sequence[str], None] = '4bffcba11b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('review_status', sa.String(), nullable=False, server_default='pending'))
    op.add_column('documents', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'reviewed_at')
    op.drop_column('documents', 'review_status')
