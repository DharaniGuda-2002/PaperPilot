"""Rebuild an investigation's report from its stored evidence, e.g. after the
comparison or report rules change. Creates a new version; earlier versions
are kept.

    python -m app.ops.reports rebuild <investigation_id>
"""

import argparse
import sys
import uuid

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.investigations.models import Investigation
from app.reports.service import assemble_report, pipeline_state, save_report


def rebuild(investigation_id: uuid.UUID) -> int:
    sessions = create_session_factory(create_db_engine(get_settings()))
    with sessions() as session, session.begin():
        investigation = session.get(Investigation, investigation_id)
        if investigation is None:
            raise SystemExit(f"Investigation {investigation_id} not found")
        finished, _ = pipeline_state(session, investigation_id)
        if not finished:
            raise SystemExit("Papers are still being processed; the report would be incomplete")
        report = assemble_report(session, investigation)
        version = save_report(session, investigation_id, report)
    print(
        f"Report version {version}: {report.overall_strength} evidence, "
        f"{len(report.key_findings)} key findings"
    )
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("rebuild").add_argument("investigation_id", type=uuid.UUID)
    args = parser.parse_args(argv)
    rebuild(args.investigation_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
