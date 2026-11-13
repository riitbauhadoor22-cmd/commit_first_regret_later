"""0003 — adds savings_goals.category (optional, e.g. "Phone") so a goal can use its own CPI inflation rate.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    with op.batch_alter_table('savings_goals') as batch_op:  # batch mode so it also works on SQLite
        batch_op.add_column(sa.Column('category', sa.String(length=30), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('savings_goals') as batch_op:
        batch_op.drop_column('category')
