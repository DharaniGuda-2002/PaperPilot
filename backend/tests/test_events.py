import uuid

import pytest
from pydantic import ValidationError

from app.events.envelope import (
    INVESTIGATION_REQUESTED,
    PAPER_DISCOVERED,
    EventEnvelope,
    InvestigationRequestedV1,
    PaperDiscoveredV1,
    UnknownEventError,
    new_event,
    parse_payload,
)


def requested_event() -> EventEnvelope:
    return new_event(
        INVESTIGATION_REQUESTED,
        InvestigationRequestedV1(task_id=uuid.uuid4(), question="Do GNNs beat XGBoost?"),
        investigation_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
    )


def test_envelope_round_trips_through_bytes() -> None:
    event = requested_event()
    restored = EventEnvelope.from_bytes(event.to_bytes())
    assert restored == event
    payload = parse_payload(restored, InvestigationRequestedV1)
    assert payload.question == "Do GNNs beat XGBoost?"


def test_unknown_schema_version_is_rejected() -> None:
    event = requested_event().model_copy(update={"schema_version": 99})
    with pytest.raises(UnknownEventError):
        parse_payload(event, InvestigationRequestedV1)


def test_payload_must_match_registered_model() -> None:
    with pytest.raises(UnknownEventError):
        parse_payload(requested_event(), PaperDiscoveredV1)
    with pytest.raises(TypeError):
        new_event(
            PAPER_DISCOVERED,
            InvestigationRequestedV1(task_id=uuid.uuid4(), question="wrong payload type"),
            investigation_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            correlation_id=uuid.uuid4(),
        )


def test_envelope_rejects_unexpected_fields() -> None:
    raw = requested_event().model_dump(mode="json") | {"surprise": True}
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


def test_payload_rejects_malformed_content() -> None:
    event = requested_event().model_copy(update={"payload": {"question": "missing task id"}})
    with pytest.raises(ValidationError):
        parse_payload(event, InvestigationRequestedV1)
