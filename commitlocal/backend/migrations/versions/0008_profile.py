"""0008 — Profile tab + registration: users.username (unique, lowercase, empty for old accounts),
users.email may be empty (phone-only accounts; still unique + lowercase), profiles.phone becomes unique
(it can be used to log in) and profiles.occupation (optional). Existing rows keep their values (new columns = NULL).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    # batch mode = SQLite copies the table with the new column; every existing row and value is kept
    with op.batch_alter_table('users') as batch:
        batch.alter_column('email', existing_type=sa.String(length=254), nullable=True)  # NULLs keep UNIQUE + CHECK working
        batch.add_column(sa.Column('username', sa.String(length=30), nullable=True))
        batch.create_unique_constraint(op.f('uq_users_username'), ['username'])
        batch.create_check_constraint(op.f('ck_users_username_lowercase'),
                                      'username IS NULL OR username = lower(username)')
    with op.batch_alter_table('profiles') as batch:
        batch.add_column(sa.Column('occupation', sa.String(length=60), nullable=True))
        batch.create_unique_constraint(op.f('uq_profiles_phone'), ['phone'])


def downgrade() -> None:
    with op.batch_alter_table('profiles') as batch:
        batch.drop_constraint(op.f('uq_profiles_phone'), type_='unique')
        batch.drop_column('occupation')
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint(op.f('ck_users_username_lowercase'), type_='check')
        batch.drop_constraint(op.f('uq_users_username'), type_='unique')
        batch.drop_column('username')
        batch.alter_column('email', existing_type=sa.String(length=254), nullable=False)
