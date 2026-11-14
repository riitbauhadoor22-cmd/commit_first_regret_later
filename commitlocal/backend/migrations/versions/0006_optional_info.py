"""0006 — optional financial information ("Permission Denied"):
- savings_settings.bank_balance_cents may be empty (= not added yet). Existing values are kept as they are.
- info_choices: the user said "I have none" for income / expenses (per month) or loans / savings.
- my_loans: loans the user chose to save on the Loans tab.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    with op.batch_alter_table('savings_settings') as batch:  # batch mode: SQLite can't ALTER a column directly
        batch.alter_column('bank_balance_cents', existing_type=sa.BigInteger(), nullable=True)

    op.create_table(
        'info_choices',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('topic', sa.String(length=10), nullable=False),
        sa.Column('month', sa.String(length=7), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("topic IN ('income', 'expenses', 'loans', 'savings')",
                           name=op.f('ck_info_choices_topic_valid')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_info_choices_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_info_choices')),
        sa.UniqueConstraint('user_id', 'topic', 'month', name='uq_info_choices_user_topic_month'),
    )
    op.create_index(op.f('ix_info_choices_user_id'), 'info_choices', ['user_id'], unique=False)

    op.create_table(
        'my_loans',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('balance_cents', sa.BigInteger(), nullable=False),
        sa.Column('annual_rate', sa.Float(), nullable=False),
        sa.Column('monthly_payment_cents', sa.BigInteger(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('balance_cents >= 0', name=op.f('ck_my_loans_balance_cents_not_negative')),
        sa.CheckConstraint('monthly_payment_cents >= 0', name=op.f('ck_my_loans_monthly_payment_cents_not_negative')),
        sa.CheckConstraint('annual_rate BETWEEN 0 AND 100', name=op.f('ck_my_loans_rate_valid')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_my_loans_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_my_loans')),
    )
    op.create_index(op.f('ix_my_loans_user_id'), 'my_loans', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_my_loans_user_id'), table_name='my_loans')
    op.drop_table('my_loans')
    op.drop_index(op.f('ix_info_choices_user_id'), table_name='info_choices')
    op.drop_table('info_choices')
    op.execute("UPDATE savings_settings SET bank_balance_cents = 0 WHERE bank_balance_cents IS NULL")
    with op.batch_alter_table('savings_settings') as batch:
        batch.alter_column('bank_balance_cents', existing_type=sa.BigInteger(), nullable=False)
