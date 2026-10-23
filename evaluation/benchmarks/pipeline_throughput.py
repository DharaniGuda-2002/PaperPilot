"""Measure discovery-pipeline throughput and latency on the local Compose stack.

Creates N investigations through the same code path as the API (investigation,
task, and outbox event in one transaction), then waits until every discovery
task has finished and reports:

- throughput: N / (last task finished - first investigation created), tasks/s
- end-to-end latency per investigation: task finished_at - investigation created_at
- processing time per task: finished_at - started_at (provider call + DB writes)
- max consumer lag observed (sampled every second)
- task distribution across Kafka partitions

Run with the workers already scaled; evaluation/benchmarks/run.sh does this for
1-4 workers using the backend virtualenv.
"""

import argparse
import json
import platform
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from confluent_kafka import Consumer, TopicPartition
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.events.envelope import TOPIC_PARTITIONS
from app.investigations import service
from app.investigations.schemas import InvestigationCreate
from app.ops.metrics import consumer_lag

RESULTS_DIR = Path(__file__).parent / "results"
GROUP = "discovery-workers"
TOPIC = "investigation-requests"


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(round(q * (len(ordered) - 1)), len(ordered) - 1)
    return ordered[index]


def committed_offsets(bootstrap: str) -> dict[int, int]:
    """discovery-workers' committed offset per investigation-requests partition."""
    consumer = Consumer(
        {"bootstrap.servers": bootstrap, "group.id": GROUP, "enable.auto.commit": False}
    )
    try:
        partitions = [TopicPartition(TOPIC, p) for p in range(TOPIC_PARTITIONS[TOPIC])]
        committed = consumer.committed(partitions, timeout=10)
        return {tp.partition: max(tp.offset, 0) for tp in committed}
    finally:
        consumer.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--label", required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()

    settings = get_settings()
    sessions = create_session_factory(create_db_engine(settings))
    run_id = uuid.uuid4().hex[:8]

    offsets_before = committed_offsets(settings.kafka_bootstrap_servers)

    # Unique questions so every task misses the search cache and calls the provider.
    ids: list[uuid.UUID] = []
    for i in range(args.n):
        with sessions() as session:
            investigation = service.create_investigation(
                session,
                InvestigationCreate(question=f"Benchmark {run_id} question number {i} about fraud"),
            )
            session.commit()
            ids.append(investigation.id)

    max_lag = 0
    deadline = time.monotonic() + args.timeout
    while True:
        with sessions() as session:
            pending = session.scalar(
                text(
                    "SELECT count(*) FROM investigation_tasks WHERE investigation_id = ANY(:ids) "
                    "AND status NOT IN ('succeeded', 'failed_permanent')"
                ),
                {"ids": ids},
            )
        max_lag = max(
            max_lag,
            sum(consumer_lag(settings.kafka_bootstrap_servers, GROUP, TOPIC).values()),
        )
        if pending == 0:
            break
        if time.monotonic() > deadline:
            print(f"timed out with {pending} tasks unfinished", file=sys.stderr)
            return 1
        time.sleep(1)

    with sessions() as session:
        rows = session.execute(
            text(
                """
                SELECT t.status,
                       extract(epoch FROM t.finished_at - i.created_at) AS end_to_end,
                       extract(epoch FROM t.finished_at - t.started_at) AS processing,
                       i.created_at, t.finished_at
                  FROM investigation_tasks t JOIN investigations i ON i.id = t.investigation_id
                 WHERE i.id = ANY(:ids)
                """
            ),
            {"ids": ids},
        ).all()

    offsets_after = committed_offsets(settings.kafka_bootstrap_servers)
    per_partition = {p: offsets_after[p] - offsets_before.get(p, 0) for p in offsets_after}

    succeeded = [r for r in rows if r.status == "succeeded"]
    end_to_end = [float(r.end_to_end) for r in succeeded]
    processing = [float(r.processing) for r in succeeded]
    wall = (max(r.finished_at for r in rows) - min(r.created_at for r in rows)).total_seconds()

    result = {
        "label": args.label,
        "workers": args.workers,
        "n": args.n,
        "succeeded": len(succeeded),
        "failed": len(rows) - len(succeeded),
        "simulated_provider_latency_ms": settings.fixture_provider_latency_ms,
        "wall_seconds": round(wall, 2),
        "throughput_per_second": round(len(rows) / wall, 2),
        "end_to_end_seconds": {
            "p50": round(statistics.median(end_to_end), 2),
            "p95": round(percentile(end_to_end, 0.95), 2),
            "max": round(max(end_to_end), 2),
        },
        "processing_seconds": {
            "p50": round(statistics.median(processing), 3),
            "p95": round(percentile(processing, 0.95), 3),
        },
        "max_consumer_lag": max_lag,
        "messages_per_partition": per_partition,
        "recorded_at": datetime.now(UTC).isoformat(),
        "machine": f"{platform.system()} {platform.machine()}",
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{args.label}.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
