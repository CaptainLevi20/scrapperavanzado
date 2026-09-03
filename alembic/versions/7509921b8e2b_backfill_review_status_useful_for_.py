"""backfill review_status useful for existing csj and consejo de estado docs

Revision ID: 7509921b8e2b
Revises: 07ba6cc26b17
Create Date: 2026-09-03 15:35:22.626048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7509921b8e2b'
down_revision: Union[str, Sequence[str], None] = '07ba6cc26b17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Marca como "useful" los documentos YA guardados de CSJ y Consejo de
    Estado que no lo estén (tanto "pending" como "not_useful"): la política del
    equipo de fuentes es que todo lo de esas cortes es útil, sin excepciones
    (ver 07ba6cc26b17, que puso el auto_review_status para lo que entra de aquí
    en adelante). Idempotente."""
    op.execute(
        """
        UPDATE documents d
        SET review_status = 'useful', reviewed_at = now()
        FROM sources s
        WHERE s.id = d.source_id
          AND s.name IN ('CSJ', 'Consejo de Estado')
          AND d.review_status <> 'useful'
        """
    )


def downgrade() -> None:
    """No reversible: no se guarda cuáles estaban en "pending" vs "not_useful"
    antes del backfill, así que volver a "pending" en masa borraría decisiones
    manuales de revisión. Se deja como no-op a propósito."""
    pass
