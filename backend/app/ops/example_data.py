"""Export one finished investigation to a JSON file, and import it elsewhere.

    python -m app.ops.example_data export <investigation_id> <file.json>
    python -m app.ops.example_data import <file.json>

The public demo has no workers, so its investigations never finish. Importing
a real run (made on a local install) lets visitors open a finished report.

What moves: the investigation, its tasks, the papers it found with their
document metadata, evidence records with validation checks, and the latest
report. What does not: extracted full text, text chunks, and embeddings.
Evidence rows keep their quotation and page; their chunk link is dropped.

Import is safe to repeat: it replaces the same investigation id, and reuses a
paper that already exists (matched on provider and provider id). It only needs
INSERT, UPDATE and DELETE, so it works under the least-privilege role.
"""

import argparse
import json
import sys
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Column, Table, delete, insert, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register every table)
from app.core.config import get_settings
from app.core.db import Base, create_db_engine, create_session_factory
from app.documents.models import PaperDocument
from app.evidence.models import EvidenceRecord, EvidenceValidation
from app.investigations.models import Investigation, InvestigationPaper, InvestigationTask
from app.papers.models import Paper
from app.reports.models import InvestigationReport

FORMAT_VERSION = 1


def _table(model: Any) -> Table:
    return Base.metadata.tables[model.__tablename__]


def _encode(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _decode(column: Column[Any], value: Any) -> Any:
    if value is None:
        return None
    python_type = column.type.python_type
    if python_type is uuid.UUID:
        return uuid.UUID(value)
    if python_type is datetime:
        return datetime.fromisoformat(value)
    return value


def _rows(session: Session, model: type, *where: Any) -> list[dict[str, Any]]:
    table = _table(model)
    result = session.execute(select(table).where(*where)).mappings().all()
    return [{key: _encode(value) for key, value in row.items()} for row in result]


def export_investigation(session: Session, investigation_id: uuid.UUID) -> dict[str, Any]:
    investigation = session.get(Investigation, investigation_id)
    if investigation is None:
        raise LookupError(f"investigation {investigation_id} not found")
    if investigation.status not in ("completed", "partially_completed"):
        raise ValueError("only a finished investigation can be exported")

    links = _rows(
        session, InvestigationPaper, InvestigationPaper.investigation_id == investigation_id
    )
    paper_ids = [uuid.UUID(link["paper_id"]) for link in links]
    evidence = _rows(session, EvidenceRecord, EvidenceRecord.investigation_id == investigation_id)
    for row in evidence:
        row["chunk_id"] = None  # chunks are not exported
    evidence_ids = [uuid.UUID(row["id"]) for row in evidence]

    latest = session.scalars(
        select(InvestigationReport)
        .where(InvestigationReport.investigation_id == investigation_id)
        .order_by(InvestigationReport.version.desc())
        .limit(1)
    ).first()
    reports = (
        _rows(session, InvestigationReport, InvestigationReport.id == latest.id) if latest else []
    )

    rows = {
        "investigations": _rows(session, Investigation, Investigation.id == investigation_id),
        "investigation_tasks": _rows(
            session, InvestigationTask, InvestigationTask.investigation_id == investigation_id
        ),
        "papers": _rows(session, Paper, Paper.id.in_(paper_ids)),
        "investigation_papers": links,
        "paper_documents": _rows(session, PaperDocument, PaperDocument.paper_id.in_(paper_ids)),
        "evidence_records": evidence,
        "evidence_validations": _rows(
            session, EvidenceValidation, EvidenceValidation.evidence_id.in_(evidence_ids)
        ),
        "investigation_reports": reports,
    }
    rows["investigations"][0]["is_example"] = True
    return {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "note": "A real run from a local PaperPilot install; no text chunks or embeddings.",
        "tables": rows,
    }


def import_investigation(session: Session, data: dict[str, Any]) -> uuid.UUID:
    if data.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"unsupported format_version {data.get('format_version')!r}")
    tables: dict[str, list[dict[str, Any]]] = data["tables"]
    investigation_id = uuid.UUID(tables["investigations"][0]["id"])

    def decode(model: type, row: dict[str, Any]) -> dict[str, Any]:
        table = _table(model)
        return {
            name: _decode(table.c[name], value) for name, value in row.items() if name in table.c
        }

    # Reuse papers the target already has; point every row at the existing id.
    remap: dict[str, str] = {}
    papers = _table(Paper)
    for row in tables["papers"]:
        existing = session.scalar(
            select(papers.c.id).where(
                papers.c.provider == row["provider"], papers.c.provider_id == row["provider_id"]
            )
        )
        if existing is not None:
            remap[row["id"]] = str(existing)
    for name in ("investigation_papers", "paper_documents", "evidence_records"):
        for row in tables[name]:
            row["paper_id"] = remap.get(row["paper_id"], row["paper_id"])

    session.execute(delete(Investigation).where(Investigation.id == investigation_id))
    new_papers = [r for r in tables["papers"] if r["id"] not in remap]
    if new_papers:
        session.execute(insert(papers), [decode(Paper, r) for r in new_papers])
    session.execute(
        insert(_table(Investigation)), [decode(Investigation, r) for r in tables["investigations"]]
    )
    for model, name in (
        (InvestigationTask, "investigation_tasks"),
        (InvestigationPaper, "investigation_papers"),
        (EvidenceRecord, "evidence_records"),
        (EvidenceValidation, "evidence_validations"),
        (InvestigationReport, "investigation_reports"),
    ):
        if tables[name]:
            session.execute(insert(_table(model)), [decode(model, r) for r in tables[name]])
    # A paper may already have a document row (unique per paper): keep the target's own.
    documents = _table(PaperDocument)
    for row in tables["paper_documents"]:
        has_document = session.scalar(
            select(documents.c.id).where(documents.c.paper_id == uuid.UUID(row["paper_id"]))
        )
        if has_document is None:
            session.execute(insert(documents), [decode(PaperDocument, row)])
    session.commit()
    return investigation_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("investigation_id", type=uuid.UUID)
    export.add_argument("file")
    load = commands.add_parser("import")
    load.add_argument("file")
    args = parser.parse_args(argv)

    engine = create_db_engine(get_settings())
    try:
        with create_session_factory(engine)() as session:
            if args.command == "export":
                data = export_investigation(session, args.investigation_id)
                with open(args.file, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=1, ensure_ascii=False)
                print(f"exported {args.investigation_id} to {args.file}")
            else:
                with open(args.file, encoding="utf-8") as handle:
                    data = json.load(handle)
                investigation_id = import_investigation(session, data)
                print(f"imported investigation {investigation_id}")
    except (LookupError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
