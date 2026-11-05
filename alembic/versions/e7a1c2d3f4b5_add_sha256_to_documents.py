"""add sha256 (huella digital) to documents and document_versions

Revision ID: e7a1c2d3f4b5
Revises: b784eb6767d9
Create Date: 2026-11-05 15:00:00.000000

Huella digital SHA-256 del archivo descargado: sirve para encontrar un archivo
que resulte malicioso y rastrear a qué productos llegó. Columnas nullable: lo
ya guardado se llena después con `python -m core.backfill_sha256`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a1c2d3f4b5'
down_revision: Union[str, Sequence[str], None] = 'b784eb6767d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('sha256', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_documents_sha256'), 'documents', ['sha256'], unique=False)
    op.add_column('document_versions', sa.Column('sha256', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_document_versions_sha256'), 'document_versions', ['sha256'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_document_versions_sha256'), table_name='document_versions')
    op.drop_column('document_versions', 'sha256')
    op.drop_index(op.f('ix_documents_sha256'), table_name='documents')
    op.drop_column('documents', 'sha256')
