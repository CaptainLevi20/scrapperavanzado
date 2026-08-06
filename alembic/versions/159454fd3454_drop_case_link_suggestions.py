"""drop case link suggestions

Revision ID: 159454fd3454
Revises: 63378f15bb90
Create Date: 2026-08-05 21:58:57.185729

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '159454fd3454'
down_revision: Union[str, Sequence[str], None] = '63378f15bb90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('case_link_suggestions')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        'case_link_suggestions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id_a', sa.Integer(), nullable=False),
        sa.Column('radicado_a', sa.String(), nullable=False),
        sa.Column('source_id_b', sa.Integer(), nullable=False),
        sa.Column('radicado_b', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('matched_digits', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['source_id_a'], ['sources.id']),
        sa.ForeignKeyConstraint(['source_id_b'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id_a', 'radicado_a', 'source_id_b', 'radicado_b', name='uq_case_link_suggestions_pair'),
    )
