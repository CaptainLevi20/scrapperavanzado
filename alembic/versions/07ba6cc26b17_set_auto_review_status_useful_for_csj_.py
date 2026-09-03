"""set auto_review_status useful for csj and consejo de estado

Revision ID: 07ba6cc26b17
Revises: cc4800e17d47
Create Date: 2026-09-03 15:28:30.946600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07ba6cc26b17'
down_revision: Union[str, Sequence[str], None] = 'cc4800e17d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """El equipo de fuentes confirma que todo lo que traen la CSJ y el Consejo
    de Estado es útil (igual que la Corte Constitucional), así que sus
    documentos deben entrar como "useful" en vez de "pending". El seed
    (core/seed.py) ya lo hace para entornos nuevos; esto lo aplica a los que ya
    tienen las fuentes creadas. `||` de JSONB fusiona la clave sin borrar
    corp_code/corp_name del Consejo de Estado. Idempotente."""
    op.execute(
        """
        UPDATE sources
        SET family_params = family_params || '{"auto_review_status": "useful"}'::jsonb
        WHERE name IN ('CSJ', 'Consejo de Estado')
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        UPDATE sources
        SET family_params = family_params - 'auto_review_status'
        WHERE name IN ('CSJ', 'Consejo de Estado')
        """
    )
