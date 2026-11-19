"""0010 — phone numbers removed (decision 12): accounts registered with only a phone number (users.email empty) are
deleted with all their rows, the profiles.phone column is dropped, and users.email is required again.
The deleted accounts can't be brought back by downgrade().

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    bind = op.get_bind()
    phone_only = "SELECT id FROM users WHERE email IS NULL"
    # SQLite only follows ON DELETE CASCADE when foreign keys are switched on, so every owned row is deleted here
    tables = [name for name in sa.inspect(bind).get_table_names()
              if name != 'users' and 'user_id' in {c['name'] for c in sa.inspect(bind).get_columns(name)}]
    tables.sort(key=lambda name: name != 'deposits')  # deposits point at savings_goals: delete them first
    for name in tables:
        op.execute(f"DELETE FROM {name} WHERE user_id IN ({phone_only})")
    op.execute("DELETE FROM users WHERE email IS NULL")

    with op.batch_alter_table('profiles') as batch:
        batch.drop_constraint(op.f('uq_profiles_phone'), type_='unique')
        batch.drop_column('phone')
    with op.batch_alter_table('users') as batch:
        batch.alter_column('email', existing_type=sa.String(length=254), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.alter_column('email', existing_type=sa.String(length=254), nullable=True)
    with op.batch_alter_table('profiles') as batch:
        batch.add_column(sa.Column('phone', sa.String(length=20), nullable=True))
        batch.create_unique_constraint(op.f('uq_profiles_phone'), ['phone'])
