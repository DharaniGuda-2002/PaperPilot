from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.core.db import Base
from app.documents import host_schedule as host_schedule_models
from app.documents import models as document_models
from app.events import models as event_models
from app.evidence import models as evidence_models
from app.investigations import models as investigation_models
from app.papers import models as paper_models

# Importing the model modules registers their tables on Base.metadata.
_MODEL_MODULES = (
    host_schedule_models,
    document_models,
    event_models,
    evidence_models,
    investigation_models,
    paper_models,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests pass an explicit URL via config attributes; otherwise use app settings.
    url = config.attributes.get("database_url")
    return str(url) if url else get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
