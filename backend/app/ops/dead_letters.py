"""Inspect and replay dead-lettered messages.

    python -m app.ops.dead_letters list [--limit 50]
    python -m app.ops.dead_letters show <dead_letter_id>
    python -m app.ops.dead_letters replay <dead_letter_id> [--dry-run]

Reading never commits offsets, so inspection does not change anything.

Replay re-enqueues the original event through the outbox as a *new* event:
new event_id (consumers already recorded the old one as processed), with
causation_id pointing at the original. For investigation.requested it also
resets the task to pending and the investigation to queued, so the worker
starts a fresh set of attempts. Fix the cause first: replaying a message that
will fail again only dead-letters it again.
"""

import argparse
import json
import sys
import uuid
from collections.abc import Iterator

from confluent_kafka import Consumer, TopicPartition
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.events.dead_letter import DEAD_LETTER_TOPIC, DeadLetterRecord
from app.events.envelope import (
    INVESTIGATION_REQUESTED,
    EventEnvelope,
    InvestigationRequestedV1,
    new_event,
    parse_payload,
    spec_for,
)
from app.events.outbox import enqueue
from app.investigations.models import Investigation, InvestigationStatus, InvestigationTask


class ReplayError(ValueError):
    pass


def read_dead_letters(bootstrap_servers: str) -> Iterator[DeadLetterRecord]:
    """Read the whole dead-letter topic without joining a consumer group."""
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": f"dead-letter-inspector-{uuid.uuid4()}",
            "enable.auto.commit": False,
        }
    )
    try:
        metadata = consumer.list_topics(DEAD_LETTER_TOPIC, timeout=10)
        partitions = metadata.topics[DEAD_LETTER_TOPIC].partitions
        ends: dict[int, int] = {}
        assignment = []
        for partition in partitions:
            low, high = consumer.get_watermark_offsets(
                TopicPartition(DEAD_LETTER_TOPIC, partition), timeout=10
            )
            if high > low:
                ends[partition] = high
                assignment.append(TopicPartition(DEAD_LETTER_TOPIC, partition, low))
        consumer.assign(assignment)
        while ends:
            message = consumer.poll(5)
            if message is None:
                break
            if message.error():
                continue
            partition, offset = message.partition(), message.offset()
            assert partition is not None and offset is not None
            yield DeadLetterRecord.model_validate_json(message.value() or b"")
            if offset + 1 >= ends[partition]:
                del ends[partition]
    finally:
        consumer.close()


def replay(session: Session, record: DeadLetterRecord) -> EventEnvelope:
    """Stage the replay in the caller's transaction; returns the new event."""
    original = record.original_envelope()
    if original is None:
        raise ReplayError("the original message is not a valid event; it cannot be replayed")
    spec = spec_for(original)
    replayed = new_event(
        spec,
        spec.payload_model.model_validate(original.payload),
        investigation_id=original.investigation_id,
        entity_id=original.entity_id,
        correlation_id=original.correlation_id,
        causation_id=original.event_id,
    )
    if spec is INVESTIGATION_REQUESTED:
        payload = parse_payload(original, InvestigationRequestedV1)
        session.execute(
            update(InvestigationTask)
            .where(InvestigationTask.id == payload.task_id)
            .values(
                status="pending",
                attempts=0,
                next_attempt_at=None,
                finished_at=None,
                last_error=f"Replayed from dead letter {record.dead_letter_id}",
            )
        )
        session.execute(
            update(Investigation)
            .where(Investigation.id == original.investigation_id)
            .values(status=InvestigationStatus.QUEUED)
        )
    partition_key = record.original_key or str(original.investigation_id)
    enqueue(session, replayed, partition_key=partition_key)
    return replayed


def _summary(record: DeadLetterRecord) -> str:
    return (
        f"{record.dead_letter_id}  {record.dead_lettered_at:%Y-%m-%d %H:%M:%S}  "
        f"{record.failure_kind:<17} {record.event_type or '-':<24} "
        f"{record.original_topic}[{record.original_partition}]@{record.original_offset}  "
        f"{record.reason[:80]}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    list_cmd = commands.add_parser("list")
    list_cmd.add_argument("--limit", type=int, default=50)
    commands.add_parser("show").add_argument("dead_letter_id", type=uuid.UUID)
    replay_cmd = commands.add_parser("replay")
    replay_cmd.add_argument("dead_letter_id", type=uuid.UUID)
    replay_cmd.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    records = list(read_dead_letters(settings.kafka_bootstrap_servers))

    if args.command == "list":
        if not records:
            print("No dead letters.")
        for record in records[-args.limit :]:
            print(_summary(record))
        return 0

    matches = [r for r in records if r.dead_letter_id == args.dead_letter_id]
    if not matches:
        print(f"Dead letter {args.dead_letter_id} not found", file=sys.stderr)
        return 1
    record = matches[0]

    if args.command == "show":
        detail = record.model_dump(mode="json")
        envelope = record.original_envelope()
        detail["original_event"] = envelope.model_dump(mode="json") if envelope else None
        print(json.dumps(detail, indent=2))
        return 0

    session_factory = create_session_factory(create_db_engine(settings))
    with session_factory() as session:
        try:
            replayed = replay(session, record)
        except ReplayError as exc:
            print(f"Cannot replay: {exc}", file=sys.stderr)
            return 1
        if args.dry_run:
            session.rollback()
            print(f"Dry run: would enqueue {replayed.event_type} as {replayed.event_id}")
            return 0
        session.commit()
    print(f"Replayed as {replayed.event_type} {replayed.event_id} (via the outbox)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
