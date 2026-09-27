# -*- coding: utf-8 -*-
"""Alembic environment.

The database location comes from PA_GATEWAY_DB (the same variable the app uses), so
a migration run and the running service always agree on which file they touch.
"""
from __future__ import annotations
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # migrations are written explicitly, not auto-generated


def _database_url() -> str:
    override = context.get_x_argument(as_dictionary=True).get("db")
    path = override or os.environ.get("PA_GATEWAY_DB", "pa-gateway.db")
    if path.startswith("sqlite"):
        return path
    return f"sqlite:///{os.path.abspath(path)}"


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
