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
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=connection.dialect.name == "sqlite",  # SQLite needs "batch" mode to change tables
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
