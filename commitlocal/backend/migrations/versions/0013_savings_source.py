"""0013 — where savings money came from: deposits.source = income (this month's income, counts as saved this month)
or already_had (money the user already had: moves total savings and the goal / safety net, but is NOT saved this
month, same as the starting balance). Existing rows = income.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    with op.batch_alter_table('deposits') as batch:
        batch.add_column(sa.Column('source', sa.String(length=12), nullable=False, server_default='income'))
        batch.create_check_constraint(op.f('ck_deposits_source_valid'), "source IN ('income', 'already_had')")


def downgrade() -> None:
    with op.batch_alter_table('deposits') as batch:
        batch.drop_constraint(op.f('ck_deposits_source_valid'), type_='check')
        batch.drop_column('source')
