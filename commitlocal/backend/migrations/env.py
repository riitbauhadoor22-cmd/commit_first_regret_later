# migrations/env.py — tells Alembic which database to change (DATABASE_URL via database.py)
# and what the tables should look like (models.Base). Runs for every `alembic ...` command.
from logging.config import fileConfig

from alembic import context

import database
from models import Base

config = context.config
# Only set up logging for the command line (not when the app runs the migrations itself)
if config.config_file_name and "engine" not in config.attributes:
    fileConfig(config.config_file_name)


def run_migrations():
    engine = config.attributes.get("engine") or database.engine
    with engine.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        # SQLite "batch" mode copies a table and DROPS the old one. With foreign keys on, dropping `users` would
        # ON DELETE CASCADE every user's rows, so foreign keys are switched off while migrating (outside a transaction).
        if is_sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=is_sqlite,  # SQLite needs "batch" mode to change tables
        )
        with context.begin_transaction():
            context.run_migrations()
        if is_sqlite:
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


run_migrations()
