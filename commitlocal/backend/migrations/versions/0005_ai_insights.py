"""0005 — adds ai_insights (saved Groq analysis per user + month, with the data fingerprint and model)
and ai_requests (one row per Groq call, for the daily limit and the cooldown).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    op.create_table(
        'ai_insights',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('month', sa.String(length=7), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(length=80), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ai_insights_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_insights')),
        sa.UniqueConstraint('user_id', 'month', name='uq_ai_insights_user_month'),
    )
    op.create_index(op.f('ix_ai_insights_user_id'), 'ai_insights', ['user_id'], unique=False)
    op.create_table(
        'ai_requests',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('month', sa.String(length=7), nullable=False),
        sa.Column('model', sa.String(length=80), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ai_requests_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_requests')),
    )
    op.create_index(op.f('ix_ai_requests_user_id'), 'ai_requests', ['user_id'], unique=False)
    op.create_index(op.f('ix_ai_requests_created_at'), 'ai_requests', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_requests_created_at'), table_name='ai_requests')
    op.drop_index(op.f('ix_ai_requests_user_id'), table_name='ai_requests')
    op.drop_table('ai_requests')
    op.drop_index(op.f('ix_ai_insights_user_id'), table_name='ai_insights')
    op.drop_table('ai_insights')
