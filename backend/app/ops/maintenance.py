"""Routine housekeeping.

    python -m app.ops.maintenance prune-processed-events [--older-than-days 8] [--dry-run]

``processed_events`` records which events each consumer group applied. Kafka
keeps messages for 7 days, so a row older than that can never match a
redelivery. The default of 8 days leaves a day of margin. Do not lower it
below the topic retention: a replay would then re-apply events.
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.events.models import ProcessedEvent

TOPIC_RETENTION_DAYS = 7
DEFAULT_OLDER_THAN_DAYS = TOPIC_RETENTION_DAYS + 1


def prune_processed_events(
    session: Session, older_than_days: int = DEFAULT_OLDER_THAN_DAYS, dry_run: bool = False
) -> int:
    """Delete (or, with dry_run, count) rows older than the cutoff. Returns the row count."""
    if older_than_days <= TOPIC_RETENTION_DAYS:
        raise ValueError(
            f"older_than_days must exceed the {TOPIC_RETENTION_DAYS}-day topic retention"
        )
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    if dry_run:
        return (
            session.scalar(
                select(func.count())
                .select_from(ProcessedEvent)
                .where(ProcessedEvent.processed_at < cutoff)
            )
            or 0
        )
    result = session.execute(delete(ProcessedEvent).where(ProcessedEvent.processed_at < cutoff))
    session.commit()
    return result.rowcount  # type: ignore[attr-defined,no-any-return]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    prune = commands.add_parser("prune-processed-events")
    prune.add_argument("--older-than-days", type=int, default=DEFAULT_OLDER_THAN_DAYS)
    prune.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    engine = create_db_engine(get_settings())
    try:
        with create_session_factory(engine)() as session:
            try:
                count = prune_processed_events(session, args.older_than_days, args.dry_run)
            except ValueError as error:
                print(f"error: {error}", file=sys.stderr)
                return 2
    finally:
        engine.dispose()
    print(f"{'would delete' if args.dry_run else 'deleted'} {count} processed_events rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
