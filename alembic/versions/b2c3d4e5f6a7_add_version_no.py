"""add version_no to documents and document_versions

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "document_versions",
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "version_no")
    op.drop_column("documents", "version_no")
