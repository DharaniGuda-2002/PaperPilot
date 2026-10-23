"""Discovery handler against real Postgres with a fake provider. The event is
taken from the outbox row the API wrote, exactly as the dispatcher would send it."""

import threading
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.events.envelope import EventEnvelope
from app.workers.discovery import (
    Outcome,
    handle_investigation_requested,
    retry_delay_seconds,
    search_query,
)
from tests.fakes import FIXTURE, FakeProvider

QUESTION = "Do graph neural networks beat gradient boosting for fraud detection?"


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


@pytest.fixture
def settings(migrated_database: str) -> Settings:
    return Settings(database_url=migrated_database)


@pytest.fixture
def requested(client: TestClient, engine: Engine) -> Iterator[EventEnvelope]:
    client.post("/api/v1/investigations", json={"question": QUESTION})
    with engine.connect() as conn:
        raw = conn.scalar(text("SELECT envelope FROM outbox_events"))
    yield EventEnvelope.model_validate(raw)


def state(engine: Engine) -> dict[str, object]:
    with engine.connect() as conn:
        return {
            "investigation": conn.scalar(text("SELECT status FROM investigations")),
            "task": conn.execute(
                text("SELECT status, attempts, last_error, result_summary FROM investigation_tasks")
            ).one(),
            "links": conn.execute(
                text("SELECT rank, retrieval_method FROM investigation_papers ORDER BY rank")
            ).all(),
            "discovered_events": conn.execute(
                text(
                    "SELECT partition_key, envelope->>'causation_id' AS cause FROM outbox_events "
                    "WHERE event_type = 'paper.discovered'"
                )
            ).all(),
            "processed": conn.scalar(text("SELECT count(*) FROM processed_events")),
        }


def test_links_papers_and_announces_them(
    requested: EventEnvelope, sessions: sessionmaker[Session], settings: Settings, engine: Engine
) -> None:
    result = handle_investigation_requested(sessions, FakeProvider(), requested, settings)

    assert result.outcome == Outcome.LINKED
    assert result.papers_linked == len(FIXTURE["results"])
    s = state(engine)
    assert s["investigation"] == "running"  # later stages are not built yet
    task = s["task"]
    assert (task.status, task.attempts, task.last_error) == ("succeeded", 1, None)  # type: ignore[attr-defined]
    assert task.result_summary["papers_linked"] == 2  # type: ignore[attr-defined]
    assert s["links"] == [(1, "openalex_search"), (2, "openalex_search")]
    events = s["discovered_events"]
    assert isinstance(events, list) and len(events) == 2
    assert all(e.cause == str(requested.event_id) for e in events)
    assert s["processed"] == 1


def test_duplicate_delivery_changes_nothing(
    requested: EventEnvelope, sessions: sessionmaker[Session], settings: Settings, engine: Engine
) -> None:
    provider = FakeProvider()
    handle_investigation_requested(sessions, provider, requested, settings)
    before = state(engine)

    again = handle_investigation_requested(sessions, provider, requested, settings)

    assert again.outcome == Outcome.DUPLICATE
    assert state(engine) == before
    assert len(provider.calls) == 1


def test_concurrent_deliveries_link_papers_once(
    requested: EventEnvelope, sessions: sessionmaker[Session], settings: Settings, engine: Engine
) -> None:
    outcomes: list[Outcome] = []

    def deliver() -> None:
        outcomes.append(
            handle_investigation_requested(sessions, FakeProvider(), requested, settings).outcome
        )

    threads = [threading.Thread(target=deliver) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count(Outcome.LINKED) == 1
    assert set(outcomes) <= {Outcome.LINKED, Outcome.BUSY_ELSEWHERE, Outcome.DUPLICATE}
    s = state(engine)
    assert len(s["links"]) == 2  # type: ignore[arg-type]
    assert len(s["discovered_events"]) == 2  # type: ignore[arg-type]


def latest_retry_event(engine: Engine) -> tuple[EventEnvelope, bool]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT envelope, available_at > now() AS delayed FROM outbox_events "
                "WHERE event_type = 'investigation.requested' ORDER BY created_at DESC LIMIT 1"
            )
        ).one()
    return EventEnvelope.model_validate(row.envelope), row.delayed


def test_temporary_failure_schedules_delayed_redelivery(
    requested: EventEnvelope, sessions: sessionmaker[Session], settings: Settings, engine: Engine
) -> None:
    provider = FakeProvider()
    provider.fail = True
    result = handle_investigation_requested(sessions, provider, requested, settings)

    assert result.outcome == Outcome.RETRY_SCHEDULED
    assert result.retry_in_seconds is not None and 24 <= result.retry_in_seconds <= 36
    s = state(engine)
    assert s["investigation"] == "running"  # not failed while retries remain
    assert s["task"].status == "failed_retryable"  # type: ignore[attr-defined]
    assert "simulated outage" in s["task"].last_error  # type: ignore[attr-defined]
    retry, delayed = latest_retry_event(engine)
    assert retry.event_id != requested.event_id
    assert retry.causation_id == requested.event_id
    assert retry.correlation_id == requested.correlation_id
    assert retry.payload == requested.payload
    assert delayed  # the dispatcher will not publish it before the backoff

    # The redelivered event succeeds once the provider recovers.
    provider.fail = False
    again = handle_investigation_requested(sessions, provider, retry, settings)
    assert again.outcome == Outcome.LINKED
    task = state(engine)["task"]
    assert (task.status, task.attempts) == ("succeeded", 2)  # type: ignore[attr-defined]


def test_retries_exhausted_fails_and_requests_dead_letter(
    requested: EventEnvelope,
    sessions: sessionmaker[Session],
    migrated_database: str,
    engine: Engine,
) -> None:
    settings = Settings(database_url=migrated_database, discovery_max_attempts=2)
    provider = FakeProvider()
    provider.fail = True

    first = handle_investigation_requested(sessions, provider, requested, settings)
    assert first.outcome == Outcome.RETRY_SCHEDULED
    retry, _ = latest_retry_event(engine)
    last = handle_investigation_requested(sessions, provider, retry, settings)

    assert last.outcome == Outcome.RETRIES_EXHAUSTED
    assert last.failure_reason == "Gave up after 2 attempts: simulated outage"
    s = state(engine)
    assert s["investigation"] == "failed"
    assert s["task"].status == "failed_permanent"  # type: ignore[attr-defined]
    with engine.connect() as conn:  # no third attempt is scheduled
        count = conn.scalar(
            text("SELECT count(*) FROM outbox_events WHERE event_type = 'investigation.requested'")
        )
    assert count == 2


@pytest.mark.parametrize(("attempt", "expected"), [(1, 30), (2, 60), (3, 120), (6, 900), (9, 900)])
def test_retry_delay_is_exponential_and_capped(
    settings: Settings, attempt: int, expected: float
) -> None:
    assert retry_delay_seconds(attempt, settings, jitter=1.0) == expected
    assert 0.8 * expected <= retry_delay_seconds(attempt, settings) <= 1.2 * expected


def test_no_results_fails_without_inventing_papers(
    requested: EventEnvelope, sessions: sessionmaker[Session], settings: Settings, engine: Engine
) -> None:
    provider = FakeProvider()
    provider.empty = True
    result = handle_investigation_requested(sessions, provider, requested, settings)

    assert result.outcome == Outcome.NO_PAPERS
    s = state(engine)
    assert s["investigation"] == "failed"
    assert s["task"].status == "failed_permanent"  # type: ignore[attr-defined]
    assert s["task"].last_error == "No papers found for this question"  # type: ignore[attr-defined]


def test_stale_running_task_from_crashed_worker_is_reclaimed(
    requested: EventEnvelope, sessions: sessionmaker[Session], settings: Settings, engine: Engine
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE investigation_tasks SET status = 'running', attempts = 1, "
                "started_at = now() - interval '1 hour'"
            )
        )
    result = handle_investigation_requested(sessions, FakeProvider(), requested, settings)
    assert result.outcome == Outcome.LINKED
    assert state(engine)["task"].attempts == 2  # type: ignore[attr-defined]


def test_running_task_owned_by_live_worker_is_left_alone(
    requested: EventEnvelope, sessions: sessionmaker[Session], settings: Settings, engine: Engine
) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE investigation_tasks SET status = 'running', started_at = now()"))
    result = handle_investigation_requested(sessions, FakeProvider(), requested, settings)
    assert result.outcome == Outcome.BUSY_ELSEWHERE
    assert state(engine)["links"] == []


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("  short   question  ", "short question"),
        ("word " * 60, ("word " * 40).strip()),
    ],
)
def test_search_query_trims_at_word_boundary(question: str, expected: str) -> None:
    assert search_query(question) == expected
    assert len(search_query(question)) <= 200


def test_api_exposes_tasks_papers_and_backlog(
    client: TestClient,
    requested: EventEnvelope,
    sessions: sessionmaker[Session],
    settings: Settings,
) -> None:
    investigation = f"/api/v1/investigations/{requested.investigation_id}"
    assert client.get("/api/v1/system/pipeline").json()["outbox_backlog"] == 1
    assert client.get(f"{investigation}/tasks").json()[0]["status"] == "pending"
    assert client.get(f"{investigation}/papers").json()["total"] == 0

    handle_investigation_requested(sessions, FakeProvider(), requested, settings)

    tasks = client.get(f"{investigation}/tasks").json()
    assert [(t["kind"], t["status"]) for t in tasks] == [("discover_papers", "succeeded")]
    assert tasks[0]["result_summary"]["papers_linked"] == 2
    papers = client.get(f"{investigation}/papers", params={"limit": 1}).json()
    assert papers["total"] == 2
    assert papers["items"][0]["rank"] == 1
    assert papers["items"][0]["paper"]["provider_id"] == "W3022945404"
    assert papers["items"][0]["retrieval_method"] == "openalex_search"


def test_task_and_paper_endpoints_404_for_unknown_investigation(client: TestClient) -> None:
    missing = "/api/v1/investigations/00000000-0000-0000-0000-000000000000"
    assert client.get(f"{missing}/tasks").status_code == 404
    assert client.get(f"{missing}/papers").status_code == 404
