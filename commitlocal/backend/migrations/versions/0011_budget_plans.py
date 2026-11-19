"""0011 — budget plans: plan_history (which plan from which month, why) and expenses.weekly (a fixed bill paid every
week). Existing rows are kept; existing expenses get weekly = false. Month results are worked out when viewed.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    with op.batch_alter_table('expenses') as batch:
        batch.add_column(sa.Column('weekly', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'plan_history',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('plan_id', sa.String(length=30), nullable=False),
        sa.Column('start_month', sa.String(length=7), nullable=False),
        sa.Column('end_month', sa.String(length=7), nullable=True),
        sa.Column('reason', sa.String(length=30), nullable=False),
        sa.Column('reason_note', sa.String(length=100), nullable=False),
        sa.Column('was_recommended', sa.Boolean(), nullable=False),
        sa.Column('requested_month', sa.String(length=7), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_plan_history_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_plan_history')),
    )
    op.create_index(op.f('ix_plan_history_user_id'), 'plan_history', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_plan_history_user_id'), table_name='plan_history')
    op.drop_table('plan_history')
    with op.batch_alter_table('expenses') as batch:
        batch.drop_column('weekly')
