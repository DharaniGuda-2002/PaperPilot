"""Versioned event contracts.

Every Kafka message is an EventEnvelope serialized as JSON. The envelope is
stable; each (event_type, schema_version) pair has its own payload model. A
reader that sees an unknown pair rejects the event instead of guessing.

Payloads carry identifiers and small metadata only, never document content.
PostgreSQL holds the authoritative state; events say "this is ready".
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Topic name -> partition count. Created by infra (kafka-init), never auto-created.
TOPIC_PARTITIONS = {
    "investigation-requests": 3,
    "paper-discovered": 6,
    "document-processed": 6,
    "evidence-extracted": 3,
    "investigation-failures": 1,
}


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: uuid.UUID
    event_type: str
    schema_version: int = Field(ge=1)
    investigation_id: uuid.UUID
    entity_id: uuid.UUID
    occurred_at: datetime
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None
    payload: dict[str, Any]

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "EventEnvelope":
        return cls.model_validate_json(raw)


class InvestigationRequestedV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: uuid.UUID
    question: str


class PaperDiscoveredV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: uuid.UUID
    rank: int
    relevance_score: float | None
    full_text_availability: str


class DocumentProcessedV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: uuid.UUID
    document_id: uuid.UUID
    content_kind: str  # full_text | abstract | none
    chunk_count: int


class EvidenceExtractedV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: uuid.UUID
    records: int
    verified: int
    rejected: int


class EventSpec(BaseModel):
    event_type: str
    schema_version: int
    topic: str
    payload_model: type[BaseModel]


INVESTIGATION_REQUESTED = EventSpec(
    event_type="investigation.requested",
    schema_version=1,
    topic="investigation-requests",
    payload_model=InvestigationRequestedV1,
)
PAPER_DISCOVERED = EventSpec(
    event_type="paper.discovered",
    schema_version=1,
    topic="paper-discovered",
    payload_model=PaperDiscoveredV1,
)

DOCUMENT_PROCESSED = EventSpec(
    event_type="document.processed",
    schema_version=1,
    topic="document-processed",
    payload_model=DocumentProcessedV1,
)
EVIDENCE_EXTRACTED = EventSpec(
    event_type="evidence.extracted",
    schema_version=1,
    topic="evidence-extracted",
    payload_model=EvidenceExtractedV1,
)

_REGISTRY = {
    (s.event_type, s.schema_version): s
    for s in (INVESTIGATION_REQUESTED, PAPER_DISCOVERED, DOCUMENT_PROCESSED, EVIDENCE_EXTRACTED)
}


class UnknownEventError(ValueError):
    """No payload model is registered for this (event_type, schema_version)."""


def new_event(
    spec: EventSpec,
    payload: BaseModel,
    *,
    investigation_id: uuid.UUID,
    entity_id: uuid.UUID,
    correlation_id: uuid.UUID,
    causation_id: uuid.UUID | None = None,
) -> EventEnvelope:
    if not isinstance(payload, spec.payload_model):
        raise TypeError(
            f"{spec.event_type} v{spec.schema_version} needs {spec.payload_model.__name__}"
        )
    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type=spec.event_type,
        schema_version=spec.schema_version,
        investigation_id=investigation_id,
        entity_id=entity_id,
        occurred_at=datetime.now(UTC),
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=payload.model_dump(mode="json"),
    )


def spec_for(envelope: EventEnvelope) -> EventSpec:
    spec = _REGISTRY.get((envelope.event_type, envelope.schema_version))
    if spec is None:
        raise UnknownEventError(f"{envelope.event_type} v{envelope.schema_version}")
    return spec


def parse_payload[T: BaseModel](envelope: EventEnvelope, model: type[T]) -> T:
    """Validate the payload against the model registered for this envelope."""
    spec = spec_for(envelope)
    if spec.payload_model is not model:
        raise UnknownEventError(
            f"{envelope.event_type} v{envelope.schema_version} is not {model.__name__}"
        )
    return model.model_validate(envelope.payload)
