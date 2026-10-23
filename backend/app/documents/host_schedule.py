"""Shared per-host request spacing, coordinated through Postgres.

Every worker reserves its next request slot with one atomic UPDATE, so the
combined request rate to a host respects its interval no matter how many
workers run. (Redis would also work; Postgres is already here and the volume
is tiny.)
"""

from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.core.db import Base

_RESERVE_SQL = text(
    """
    INSERT INTO fetch_host_schedule AS s (host, next_slot_at)
    VALUES (:host, now() + make_interval(secs => :interval))
    ON CONFLICT (host) DO UPDATE
       SET next_slot_at = greatest(s.next_slot_at, now()) + make_interval(secs => :interval)
    RETURNING extract(epoch FROM (s.next_slot_at - make_interval(secs => :interval)) - now())
    """
)


class FetchHostSchedule(Base):
    __tablename__ = "fetch_host_schedule"

    host: Mapped[str] = mapped_column(String(255), primary_key=True)
    # The earliest time the *next* reservation may start.
    next_slot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PostgresHostScheduler:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def reserve(self, host: str, interval_seconds: float) -> float:
        with self._sessions() as session, session.begin():
            wait = session.execute(
                _RESERVE_SQL, {"host": host.lower(), "interval": interval_seconds}
            ).scalar_one()
        return max(float(wait), 0.0)
