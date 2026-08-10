"""add index on documents.title

The general document listing (repository.list_documents with
collapse_case_families) evaluates a correlated EXISTS subquery that self-joins
documents on equal titles within the same source family. Without an index on
documents.title, that subquery sequentially scans the entire documents table
once per row — an O(n^2) plan whose cost lands almost entirely on the
total-count query for the unfiltered /documents view. Measured on ~9.6k rows it
took ~35s per page load; with this index it drops to well under a second.

Revision ID: a1b2c3d4e5f6
Revises: 159454fd3454
Create Date: 2026-08-10 15:35:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '159454fd3454'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_documents_title', 'documents', ['title'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_documents_title', table_name='documents')
