"""0012 — real savings: a deposit row is now money put in (kind = deposit) or taken out (kind = withdrawal) of one
place: general savings, the safety net or a goal. Existing rows are kept as deposits (goal_id set → goal, else the
safety net, which is what they were before). Also removes plan_results if an earlier draft of 0011 made it (plan
month results are now worked out when viewed, never stored).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    with op.batch_alter_table('deposits') as batch:
        batch.add_column(sa.Column('kind', sa.String(length=10), nullable=False, server_default='deposit'))
        batch.add_column(sa.Column('place', sa.String(length=10), nullable=False, server_default='safety_net'))
        batch.create_check_constraint(op.f('ck_deposits_kind_valid'), "kind IN ('deposit', 'withdrawal')")
        batch.create_check_constraint(op.f('ck_deposits_place_valid'), "place IN ('general', 'safety_net', 'goal')")
    op.execute("UPDATE deposits SET place = 'goal' WHERE goal_id IS NOT NULL")
    if 'plan_results' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('plan_results')


def downgrade() -> None:
    op.execute("DELETE FROM deposits WHERE kind = 'withdrawal' OR place = 'general'")
    with op.batch_alter_table('deposits') as batch:
        batch.drop_constraint(op.f('ck_deposits_place_valid'), type_='check')
        batch.drop_constraint(op.f('ck_deposits_kind_valid'), type_='check')
        batch.drop_column('place')
        batch.drop_column('kind')
