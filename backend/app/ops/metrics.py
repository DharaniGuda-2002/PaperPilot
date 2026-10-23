"""Pipeline metrics snapshot as JSON.

    python -m app.ops.metrics [--window-minutes 60]

Reports, with definitions:
- outbox.backlog: unpublished outbox rows; oldest_due_seconds: how long the
  oldest row that is due (not a scheduled retry) has waited.
- consumer_lag[group][partition]: newest offset minus the group's committed
  offset, i.e. messages not yet processed.
- tasks.by_status: count of discovery tasks per status (all time).
- tasks.window: tasks that finished in the window. retry_rate = finished tasks
  that needed more than one attempt / finished tasks. failure_rate = finished
  as failed_permanent / finished.
- latency_seconds: for tasks succeeded in the window, p50/p95 of
  (a) processing = finished_at - started_at of the last attempt, and
  (b) end_to_end = finished_at - investigation created_at.
- throughput_per_minute: finished tasks in the window / window minutes.
"""

import argparse
import json
import uuid
from typing import Any

from confluent_kafka import Consumer, TopicPartition
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.events.outbox import outbox_backlog

GROUPS = {"discovery-workers": "investigation-requests"}


def consumer_lag(bootstrap_servers: str, group: str, topic: str) -> dict[int, int]:
    """Read the group's committed offsets without joining the group."""
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group,
            "enable.auto.commit": False,
            "client.id": f"metrics-{uuid.uuid4()}",
        }
    )
    try:
        metadata = consumer.list_topics(topic, timeout=10).topics[topic]
        partitions = [TopicPartition(topic, p) for p in sorted(metadata.partitions)]
        lag = {}
        for committed in consumer.committed(partitions, timeout=10):
            low, high = consumer.get_watermark_offsets(committed, timeout=10)
            position = committed.offset if committed.offset >= 0 else low
            lag[committed.partition] = max(high - position, 0)
        return lag
    finally:
        consumer.close()


def task_metrics(session: Session, window_minutes: int) -> dict[str, Any]:
    by_status: dict[str, int] = dict(
        session.execute(
            text("SELECT status, count(*) FROM investigation_tasks GROUP BY status")
        ).all()
    )
    window = session.execute(
        text(
            """
            WITH finished AS (
                SELECT t.status, t.attempts,
                       extract(epoch FROM t.finished_at - t.started_at) AS processing,
                       extract(epoch FROM t.finished_at - i.created_at) AS end_to_end
                  FROM investigation_tasks t
                  JOIN investigations i ON i.id = t.investigation_id
                 WHERE t.status IN ('succeeded', 'failed_permanent')
                   AND t.finished_at > now() - make_interval(mins => :window)
            ), ok AS (SELECT * FROM finished WHERE status = 'succeeded')
            SELECT (SELECT count(*) FROM finished) AS finished,
                   (SELECT count(*) FROM finished WHERE attempts > 1) AS retried,
                   (SELECT count(*) FROM finished WHERE status = 'failed_permanent') AS failed,
                   (SELECT count(*) FROM ok) AS succeeded,
                   (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY processing) FROM ok)
                       AS processing_p50,
                   (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY processing) FROM ok)
                       AS processing_p95,
                   (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY end_to_end) FROM ok)
                       AS end_to_end_p50,
                   (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY end_to_end) FROM ok)
                       AS end_to_end_p95
            """
        ),
        {"window": window_minutes},
    ).one()
    finished = window.finished or 0

    def r(value: float | None) -> float | None:
        return round(float(value), 3) if value is not None else None

    return {
        "by_status": by_status,
        "window": {
            "minutes": window_minutes,
            "finished": finished,
            "succeeded": window.succeeded,
            "retry_rate": r(window.retried / finished) if finished else None,
            "failure_rate": r(window.failed / finished) if finished else None,
            "throughput_per_minute": r(finished / window_minutes),
            "latency_seconds": {
                "processing_p50": r(window.processing_p50),
                "processing_p95": r(window.processing_p95),
                "end_to_end_p50": r(window.end_to_end_p50),
                "end_to_end_p95": r(window.end_to_end_p95),
            },
        },
    }


def snapshot(window_minutes: int, include_kafka: bool = True) -> dict[str, Any]:
    settings = get_settings()
    session_factory = create_session_factory(create_db_engine(settings))
    with session_factory() as session:
        backlog, oldest = outbox_backlog(session)
        tasks = task_metrics(session, window_minutes)
    result: dict[str, Any] = {
        "outbox": {"backlog": backlog, "oldest_due_seconds": oldest},
        "tasks": tasks,
    }
    if include_kafka:
        result["consumer_lag"] = {
            group: consumer_lag(settings.kafka_bootstrap_servers, group, topic)
            for group, topic in GROUPS.items()
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--no-kafka", action="store_true", help="skip consumer lag")
    args = parser.parse_args()
    print(json.dumps(snapshot(args.window_minutes, not args.no_kafka), indent=2, default=str))


if __name__ == "__main__":
    main()
