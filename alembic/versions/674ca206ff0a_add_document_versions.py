"""add document versions

Revision ID: 674ca206ff0a
Revises: 465c6f3e4a45
Create Date: 2026-07-16 21:03:39.863819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '674ca206ff0a'
down_revision: Union[str, Sequence[str], None] = '465c6f3e4a45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('run_sources', sa.Column('docs_updated', sa.Integer(), nullable=False, server_default='0'))
    op.create_table(
        'document_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('storage_bucket', sa.String(), nullable=False),
        sa.Column('storage_key', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=True),
        sa.Column('file_extension', sa.String(), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('converted_format', sa.String(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('document_versions')
    op.drop_column('run_sources', 'docs_updated')
