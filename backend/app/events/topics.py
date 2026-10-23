"""Create the Kafka topics PaperPilot uses. Idempotent: existing topics are kept.

Run once per environment: python -m app.events.topics
"""

import logging
import sys
import time

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.events.envelope import TOPIC_PARTITIONS

logger = logging.getLogger(__name__)

RETENTION_MS = str(7 * 24 * 3600 * 1000)  # a week of history for replay


def ensure_topics(bootstrap_servers: str, replication_factor: int = 1) -> list[str]:
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    existing = set(admin.list_topics(timeout=10).topics)
    missing = [
        NewTopic(
            name,
            num_partitions=partitions,
            replication_factor=replication_factor,
            config={"retention.ms": RETENTION_MS},
        )
        for name, partitions in TOPIC_PARTITIONS.items()
        if name not in existing
    ]
    created = []
    for name, future in admin.create_topics(missing).items() if missing else []:
        future.result()
        created.append(name)
    return created


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    for attempt in range(1, 11):
        try:
            created = ensure_topics(settings.kafka_bootstrap_servers)
            logger.info("topics ready", extra={"topics_created": created})
            return
        except KafkaException as exc:
            logger.warning("kafka not ready", extra={"attempt": attempt, "error": str(exc)})
            time.sleep(3)
    sys.exit(1)


if __name__ == "__main__":
    main()
