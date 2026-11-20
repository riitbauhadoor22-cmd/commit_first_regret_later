"""0014 — month-end recap: profiles.recap_seen_month (YYYY-MM of the last recap the user has seen), so the recap
of last month is shown only once. The recap's numbers are never stored: they are worked out when shown.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    with op.batch_alter_table('profiles') as batch:
        batch.add_column(sa.Column('recap_seen_month', sa.String(length=7), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('profiles') as batch:
        batch.drop_column('recap_seen_month')
