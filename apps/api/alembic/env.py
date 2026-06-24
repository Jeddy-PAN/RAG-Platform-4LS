from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve migration URL from env, Alembic config, then app settings."""

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    configured_url = config.get_main_option("sqlalchemy.url")
    default_url = "postgresql+psycopg://rag:rag@postgres:5432/rag"
    if configured_url and configured_url != default_url:
        return configured_url

    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run Alembic without opening a database connection."""

    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run Alembic against a live PostgreSQL connection."""

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
