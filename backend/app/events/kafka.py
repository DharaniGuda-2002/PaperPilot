"""Kafka client factories. Configuration choices are explained inline because
they decide the delivery guarantees."""

from typing import Any

from confluent_kafka import Consumer, Producer


def make_producer(bootstrap_servers: str, client_id: str) -> Producer:
    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": client_id,
            # Broker de-duplicates producer retries; with acks=all a delivery report
            # means every in-sync replica has the message.
            "enable.idempotence": True,
            "acks": "all",
            "linger.ms": 5,
            # Give up (and report failure) well before the dispatcher's lease expires.
            "delivery.timeout.ms": 20_000,
        }
    )


def make_consumer(bootstrap_servers: str, group_id: str, **overrides: Any) -> Consumer:
    config: dict[str, Any] = {
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        # Offsets are committed by hand, only after results are persisted.
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        # Rebalance by moving only affected partitions instead of stopping the group.
        "partition.assignment.strategy": "cooperative-sticky",
        # A slow provider call must not get this consumer kicked out of the group.
        "max.poll.interval.ms": 300_000,
    }
    config.update(overrides)
    return Consumer(config)
