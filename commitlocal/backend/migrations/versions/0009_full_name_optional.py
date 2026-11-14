"""0009 — the Full name field was removed from Register and Profile: profiles.full_name may now be empty (NULL).
The column and every existing name are kept (no data is deleted); the app shows the username instead.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== UPGRADE / DOWNGRADE =====
def upgrade() -> None:
    # batch mode = SQLite copies the table with the changed column; every existing row and value is kept
    with op.batch_alter_table('profiles') as batch:
        batch.alter_column('full_name', existing_type=sa.String(length=100), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE profiles SET full_name = '' WHERE full_name IS NULL")  # NOT NULL again needs a value
    with op.batch_alter_table('profiles') as batch:
        batch.alter_column('full_name', existing_type=sa.String(length=100), nullable=False)
