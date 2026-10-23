"""Integration tests against a real Kafka broker.

Each test uses its own topic and consumer group so it cannot disturb running
workers. Skipped when no broker is reachable, unless REQUIRE_KAFKA=1 (CI).
"""

import os
import threading
import time
import uuid
from collections.abc import Callable, Iterator

import pytest
from confluent_kafka import Consumer, KafkaException, Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.events.dead_letter import DEAD_LETTER_TOPIC, DeadLetterRecord
from app.events.envelope import (
    INVESTIGATION_REQUESTED,
    EventEnvelope,
    InvestigationRequestedV1,
    new_event,
)
from app.events.topics import ensure_topics
from app.ops.dead_letters import read_dead_letters
from app.ops.metrics import consumer_lag
from app.workers.consumer import HandlerResult, run_consumer
from app.workers.outbox_dispatcher import KafkaPublisher, dispatch_once

BOOTSTRAP = os.environ.get("KAFKA_TEST_BOOTSTRAP", "127.0.0.1:9094")


@pytest.fixture(scope="module")
def kafka() -> str:
    try:
        AdminClient({"bootstrap.servers": BOOTSTRAP}).list_topics(timeout=3)
    except KafkaException:
        if os.environ.get("REQUIRE_KAFKA") == "1":
            raise
        pytest.skip(f"no Kafka broker at {BOOTSTRAP}")
    ensure_topics(BOOTSTRAP)
    return BOOTSTRAP


@pytest.fixture
def topic(kafka: str) -> Iterator[str]:
    name = f"test-{uuid.uuid4().hex[:12]}"
    admin = AdminClient({"bootstrap.servers": kafka})
    admin.create_topics([NewTopic(name, num_partitions=2, replication_factor=1)])[name].result()
    yield name
    admin.delete_topics([name])[name].result()


def envelope(question: str = "Do GNNs beat XGBoost on fraud detection?") -> EventEnvelope:
    return new_event(
        INVESTIGATION_REQUESTED,
        InvestigationRequestedV1(task_id=uuid.uuid4(), question=question),
        investigation_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
    )


def produce(kafka: str, topic: str, values: list[bytes]) -> None:
    producer = Producer({"bootstrap.servers": kafka})
    for value in values:
        producer.produce(topic, key=b"k", value=value)  # one key: same partition, in order
    assert producer.flush(10) == 0


def wait_for(condition: Callable[[], bool], timeout: float = 45, interval: float = 1.0) -> None:
    # Each check may open a Kafka client; polling once a second keeps client churn low.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise AssertionError("condition not met in time")


def dead_letters_for(kafka: str, topic: str) -> list[DeadLetterRecord]:
    return [r for r in read_dead_letters(kafka) if r.original_topic == topic]


def test_consumer_dead_letters_bad_messages_and_keeps_going(kafka: str, topic: str) -> None:
    poison = b"{not an envelope"
    always_fails = envelope("this one always raises")
    gives_up = envelope("this one exhausts its retries")
    good = envelope("this one succeeds")
    handled: list[str] = []
    calls: dict[str, int] = {}

    def handler(event: EventEnvelope) -> HandlerResult:
        question = str(event.payload["question"])
        calls[question] = calls.get(question, 0) + 1
        if event.event_id == always_fails.event_id:
            raise RuntimeError("simulated bug")
        if event.event_id == gives_up.event_id:
            return HandlerResult("gave up", dead_letter_reason="Gave up after 4 attempts")
        handled.append(question)
        return HandlerResult("ok")

    produce(kafka, topic, [poison, always_fails.to_bytes(), gives_up.to_bytes(), good.to_bytes()])
    group = f"group-{uuid.uuid4().hex[:8]}"
    settings = Settings(
        database_url="postgresql+psycopg://unused@localhost/unused",
        kafka_bootstrap_servers=kafka,
        consumer_max_handler_failures=2,
    )
    stop = threading.Event()
    thread = threading.Thread(
        target=run_consumer,
        kwargs={
            "settings": settings,
            "group_id": group,
            "topic": topic,
            "handler": handler,
            "stop": stop,
        },
    )
    thread.start()
    try:
        # The good message behind the bad ones is still processed: no partition is blocked.
        wait_for(lambda: handled == ["this one succeeds"])
        wait_for(lambda: len(dead_letters_for(kafka, topic)) == 3)
        wait_for(lambda: sum(consumer_lag(kafka, group, topic).values()) == 0)
    finally:
        stop.set()
        thread.join(15)

    records = {r.failure_kind: r for r in dead_letters_for(kafka, topic)}
    assert records["unparseable"].original_value() == poison
    assert records["handler_error"].event_id == always_fails.event_id
    assert records["handler_error"].handler_failures == 2
    assert "simulated bug" in records["handler_error"].reason
    assert calls["this one always raises"] == 2  # retried, then dead-lettered
    assert records["retries_exhausted"].reason == "Gave up after 4 attempts"
    assert records["retries_exhausted"].original_envelope() == gives_up


def test_dispatcher_publishes_outbox_rows_to_kafka(
    kafka: str, topic: str, client: TestClient, engine: Engine
) -> None:
    client.post("/api/v1/investigations", json={"question": "Does contrastive learning help?"})
    with engine.begin() as conn:  # point the row at this test's topic
        conn.execute(text("UPDATE outbox_events SET topic = :t"), {"t": topic})
        expected = EventEnvelope.model_validate(
            conn.scalar(text("SELECT envelope FROM outbox_events"))
        )

    publisher = KafkaPublisher(kafka, flush_timeout_seconds=10)
    assert dispatch_once(sessionmaker(bind=engine), publisher, batch_size=10, lease_seconds=30) == (
        1,
        0,
    )

    consumer = Consumer(
        {
            "bootstrap.servers": kafka,
            "group.id": f"verify-{uuid.uuid4()}",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([topic])
    try:
        message = None
        deadline = time.monotonic() + 20
        while message is None and time.monotonic() < deadline:
            candidate = consumer.poll(1)
            if candidate is not None and not candidate.error():
                message = candidate
    finally:
        consumer.close()
    assert message is not None
    assert EventEnvelope.from_bytes(message.value() or b"") == expected
    assert message.key() == str(expected.investigation_id).encode()
    headers = dict(message.headers() or [])
    assert headers["event_type"] == b"investigation.requested"
    assert headers["schema_version"] == b"1"


def test_dead_letter_topic_exists_with_expected_partitions(kafka: str) -> None:
    metadata = AdminClient({"bootstrap.servers": kafka}).list_topics(timeout=5)
    assert len(metadata.topics[DEAD_LETTER_TOPIC].partitions) == 1
    assert len(metadata.topics["investigation-requests"].partitions) == 3
