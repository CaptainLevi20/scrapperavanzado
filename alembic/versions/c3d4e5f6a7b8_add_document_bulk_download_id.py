"""add document bulk_download_id

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('bulk_download_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'documents_bulk_download_id_fkey', 'documents', 'bulk_downloads', ['bulk_download_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('documents_bulk_download_id_fkey', 'documents', type_='foreignkey')
    op.drop_column('documents', 'bulk_download_id')
