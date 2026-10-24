"""Create or refresh the least-privilege runtime role.

    APP_DB_PASSWORD=... python -m app.ops.runtime_role [--role paperpilot_app]

Run as the database owner (the same connection migrations use), after
migrations. The role can read and write application tables and use their
sequences. It cannot create, alter, or drop anything, cannot read
``alembic_version``, and cannot create roles or databases. Default privileges
cover tables that later migrations add, provided the owner creates them.
The command is idempotent; re-run it to rotate the password.

Then point the API and workers at the new role via ``DATABASE_URL`` and keep
the owner URL in ``MIGRATION_DATABASE_URL`` for migrations only.
"""

import argparse
import os
import sys
from contextlib import closing

from psycopg import sql
from sqlalchemy import Engine

from app.core.config import get_settings
from app.core.db import create_db_engine

DEFAULT_ROLE = "paperpilot_app"
MIGRATION_TABLE = "alembic_version"


def provision(engine: Engine, role: str, password: str) -> None:
    """Create the role if needed, set its password, and apply grants."""
    if not password:
        raise ValueError("a password is required")
    ident = sql.Identifier(role)
    raw = engine.raw_connection()
    try:
        with closing(raw.cursor()) as cur:
            cur.execute("SELECT current_database(), current_user")
            row = cur.fetchone()
            assert row is not None
            database, owner = row
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            verb = "ALTER" if cur.fetchone() else "CREATE"
            cur.execute(
                sql.SQL(
                    "{} ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS"
                ).format(sql.SQL(verb), ident, sql.Literal(password))
            )
            statements = [
                "GRANT CONNECT ON DATABASE {db} TO {role}",
                "GRANT USAGE ON SCHEMA public TO {role}",
                "REVOKE CREATE ON SCHEMA public FROM {role}",
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}",
                "REVOKE ALL ON TABLE {migrations} FROM {role}",
                "ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}",
                "ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
                "GRANT USAGE, SELECT ON SEQUENCES TO {role}",
            ]
            for statement in statements:
                cur.execute(
                    sql.SQL(statement).format(
                        db=sql.Identifier(database),
                        role=ident,
                        owner=sql.Identifier(owner),
                        migrations=sql.Identifier(MIGRATION_TABLE),
                    )
                )
        raw.commit()
    finally:
        raw.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--role", default=DEFAULT_ROLE)
    args = parser.parse_args(argv)
    password = os.environ.get("APP_DB_PASSWORD", "")
    if not password:
        print("error: set APP_DB_PASSWORD in the environment", file=sys.stderr)
        return 2
    settings = get_settings()
    engine = create_db_engine(settings.model_copy(update={"database_url": settings.migration_url}))
    try:
        provision(engine, args.role, password)
    finally:
        engine.dispose()
    print(f"role {args.role} is ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
