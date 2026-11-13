"""0002 — adds profiles.language (en / fr / mfe, null = never chosen) so the language follows the user.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    with op.batch_alter_table('profiles') as batch_op:  # batch mode so it also works on SQLite
        batch_op.add_column(sa.Column('language', sa.String(length=3), nullable=True))
        batch_op.create_check_constraint(op.f('ck_profiles_language_allowed'),
                                         "language IS NULL OR language IN ('en', 'fr', 'mfe')")


def downgrade() -> None:
    with op.batch_alter_table('profiles') as batch_op:
        batch_op.drop_constraint(op.f('ck_profiles_language_allowed'), type_='check')
        batch_op.drop_column('language')
