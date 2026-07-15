"""add document preview storage key

Revision ID: 93307b0ad39a
Revises: 2da890a73147
Create Date: 2026-07-15 17:29:17.999418

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93307b0ad39a'
down_revision: Union[str, Sequence[str], None] = '2da890a73147'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('preview_storage_key', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'preview_storage_key')
