"""Report worker: consumes evidence.extracted. When every paper of an
investigation has finished the document and evidence stages, it builds the
comparison and report from persisted evidence, stores the report version,
and sets the investigation's final status, all in one transaction.

Events are keyed by investigation, so one investigation's events arrive in
order at one worker; the build_report task claim makes the build happen once
even if events are redelivered.

Run: python -m app.workers.reports
"""

import logging
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.events.envelope import EventEnvelope, EvidenceExtractedV1, parse_payload
from app.investigations.models import Investigation, TaskKind, TaskStatus
from app.reports.service import assemble_report, final_status, pipeline_state, save_report
from app.workers.consumer import HandlerResult, run_consumer
from app.workers.tasks import (
    already_processed,
    claim_task,
    ensure_task,
    finish_task,
    mark_processed,
)

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "report-workers"
TOPIC = "evidence-extracted"


@dataclass(frozen=True)
class ReportResult:
    outcome: str  # built | waiting | already_built | duplicate | investigation_missing
    version: int | None = None


def handle_evidence_extracted(
    session_factory: sessionmaker[Session], envelope: EventEnvelope
) -> ReportResult:
    parse_payload(envelope, EvidenceExtractedV1)  # validates the contract
    try:
        with session_factory() as session, session.begin():
            if already_processed(session, CONSUMER_GROUP, envelope.event_id):
                return ReportResult("duplicate")
            mark_processed(session, CONSUMER_GROUP, envelope.event_id)
            investigation = session.get(Investigation, envelope.investigation_id)
            if investigation is None:
                return ReportResult("investigation_missing")
            finished, failures = pipeline_state(session, investigation.id)
            if not finished:
                return ReportResult("waiting")  # a later paper's event will build it
            task_id = ensure_task(session, investigation.id, TaskKind.BUILD_REPORT, "")
            if task_id is None or claim_task(session, task_id) is None:
                return ReportResult("already_built")

            report = assemble_report(session, investigation)
            version = save_report(session, investigation.id, report)
            status = final_status(report, failures)
            session.execute(
                update(Investigation)
                .where(Investigation.id == investigation.id)
                .values(status=status)
            )
            finish_task(
                session,
                task_id,
                TaskStatus.SUCCEEDED,
                summary={
                    "version": version,
                    "overall_strength": report.overall_strength,
                    "findings": len(report.key_findings),
                    "final_status": status,
                },
            )
    except IntegrityError:
        return ReportResult("duplicate")
    logger.info(
        "report built",
        extra={"investigation_id": str(envelope.investigation_id), "version": version},
    )
    return ReportResult("built", version)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(create_db_engine(settings))

    def handle(envelope: EventEnvelope) -> HandlerResult:
        result = handle_evidence_extracted(session_factory, envelope)
        return HandlerResult(summary=f"{result.outcome} (v{result.version or '-'})")

    run_consumer(settings, group_id=CONSUMER_GROUP, topic=TOPIC, handler=handle)


if __name__ == "__main__":
    main()
