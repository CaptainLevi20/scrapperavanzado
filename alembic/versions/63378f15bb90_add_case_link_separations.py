"""add case link separations

Revision ID: 63378f15bb90
Revises: c2eab54563c4
Create Date: 2026-08-05 17:17:08.405012

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63378f15bb90'
down_revision: Union[str, Sequence[str], None] = 'c2eab54563c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'case_link_separations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('radicado', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'radicado', name='uq_case_link_separations_source_radicado'),
    )


def downgrade() -> None:
    op.drop_table('case_link_separations')
