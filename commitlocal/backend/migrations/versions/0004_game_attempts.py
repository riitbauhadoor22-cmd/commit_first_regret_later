"""0004 — adds game_attempts (Arcade "Budget Challenge": one row per game, score + XP given once per attempt).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    op.create_table(
        'game_attempts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('events_on', sa.Boolean(), nullable=False),
        sa.Column('event', sa.String(length=40), nullable=True),
        sa.Column('stage', sa.String(length=10), nullable=False),
        sa.Column('allocation', sa.Text(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('xp', sa.Integer(), nullable=False),
        sa.Column('xp_awarded', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint('xp >= 0', name=op.f('ck_game_attempts_xp_not_negative')),
        sa.CheckConstraint('score BETWEEN 0 AND 100', name=op.f('ck_game_attempts_score_valid')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_game_attempts_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_game_attempts')),
    )
    op.create_index(op.f('ix_game_attempts_user_id'), 'game_attempts', ['user_id'], unique=False)
    op.create_index(op.f('ix_game_attempts_created_at'), 'game_attempts', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_game_attempts_created_at'), table_name='game_attempts')
    op.drop_index(op.f('ix_game_attempts_user_id'), table_name='game_attempts')
    op.drop_table('game_attempts')
