"""add radicado and case links

Revision ID: c2eab54563c4
Revises: d071af46dc25
Create Date: 2026-08-04 15:56:30.804751

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2eab54563c4'
down_revision: Union[str, Sequence[str], None] = 'd071af46dc25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('radicado', sa.String(), nullable=True))
    op.create_index('ix_documents_radicado', 'documents', ['radicado'])

    op.create_table(
        'case_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'case_link_stages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_link_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('radicado', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['case_link_id'], ['case_links.id']),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'radicado', name='uq_case_link_stages_source_radicado'),
    )
    op.create_table(
        'case_link_suggestions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id_a', sa.Integer(), nullable=False),
        sa.Column('radicado_a', sa.String(), nullable=False),
        sa.Column('source_id_b', sa.Integer(), nullable=False),
        sa.Column('radicado_b', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('matched_digits', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['source_id_a'], ['sources.id']),
        sa.ForeignKeyConstraint(['source_id_b'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_id_a', 'radicado_a', 'source_id_b', 'radicado_b',
            name='uq_case_link_suggestions_pair',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('case_link_suggestions')
    op.drop_table('case_link_stages')
    op.drop_table('case_links')
    op.drop_index('ix_documents_radicado', table_name='documents')
    op.drop_column('documents', 'radicado')
