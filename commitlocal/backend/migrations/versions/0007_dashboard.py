"""0007 — Dashboard: weekly_budgets (planned spending per week) and earned_badges (badges are never deleted).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    op.create_table(
        'weekly_budgets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('set_on', sa.Date(), nullable=False),
        sa.CheckConstraint('amount_cents >= 0', name=op.f('ck_weekly_budgets_amount_cents_not_negative')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_weekly_budgets_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_weekly_budgets')),
    )
    op.create_index(op.f('ix_weekly_budgets_user_id'), 'weekly_budgets', ['user_id'], unique=True)
    op.create_table(
        'earned_badges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('earned_on', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_earned_badges_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_earned_badges')),
        sa.UniqueConstraint('user_id', 'code', name='uq_earned_badges_user_code'),
    )
    op.create_index(op.f('ix_earned_badges_user_id'), 'earned_badges', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_earned_badges_user_id'), table_name='earned_badges')
    op.drop_table('earned_badges')
    op.drop_index(op.f('ix_weekly_budgets_user_id'), table_name='weekly_budgets')
    op.drop_table('weekly_budgets')
