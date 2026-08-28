"""add document_versions updated_by_run_source_id

Revision ID: cc4800e17d47
Revises: c3d4e5f6a7b8
Create Date: 2026-08-28 09:16:13.523263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc4800e17d47'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('document_versions', sa.Column('updated_by_run_source_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'document_versions_updated_by_run_source_id_fkey',
        'document_versions', 'run_sources', ['updated_by_run_source_id'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('document_versions_updated_by_run_source_id_fkey', 'document_versions', type_='foreignkey')
    op.drop_column('document_versions', 'updated_by_run_source_id')
