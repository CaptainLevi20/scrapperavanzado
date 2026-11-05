"""add quarantined_files (cuarentena del antivirus)

Revision ID: f1b2c3d4e5a6
Revises: e7a1c2d3f4b5
Create Date: 2026-11-05 16:00:00.000000

Archivos descargados que el antivirus marcó como infectados. No se crea
documento: el archivo queda en el bucket de cuarentena y aquí su registro.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b2c3d4e5a6'
down_revision: Union[str, Sequence[str], None] = 'e7a1c2d3f4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'quarantined_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('run_source_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('virus', sa.String(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('storage_bucket', sa.String(), nullable=False),
        sa.Column('storage_key', sa.Text(), nullable=False),
        sa.Column('quarantined_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_source_id'], ['run_sources.id']),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quarantined_files_sha256'), 'quarantined_files', ['sha256'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_quarantined_files_sha256'), table_name='quarantined_files')
    op.drop_table('quarantined_files')
