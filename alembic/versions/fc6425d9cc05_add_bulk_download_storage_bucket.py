"""add bulk download storage bucket

Revision ID: fc6425d9cc05
Revises: 674ca206ff0a
Create Date: 2026-07-28 15:42:37.727471

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc6425d9cc05'
down_revision: Union[str, Sequence[str], None] = '674ca206ff0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('bulk_downloads', sa.Column('storage_bucket', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bulk_downloads', 'storage_bucket')
