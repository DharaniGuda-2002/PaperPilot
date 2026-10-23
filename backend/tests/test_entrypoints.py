"""Each worker process imports only its own modules. Run each entry point's
imports in a fresh interpreter (as a container would) and check that every
ORM mapping resolves. Regression: the evidence worker failed with
NoReferencedTableError because nothing imported the papers models."""

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
ENTRY_POINTS = [
    "app.main",
    "app.workers.outbox_dispatcher",
    "app.workers.discovery",
    "app.workers.documents",
    "app.workers.evidence",
    "app.workers.reports",
    "app.ops.dead_letters",
    "app.ops.metrics",
]


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_entry_point_resolves_all_tables(module: str) -> None:
    code = (
        f"import {module}\n"
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import configure_mappers\n"
        "from app.core.db import Base, create_session_factory\n"
        "create_session_factory(create_engine('postgresql+psycopg://u:p@127.0.0.1:1/none'))\n"
        "configure_mappers()\n"
        # Flushes resolve every foreign key's target table; do the same here.
        "[fk.column for t in Base.metadata.tables.values() for fk in t.foreign_keys]\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-2000:]


# Processes that run from the small `api` image, which has no PDF or ML packages.
API_IMAGE_ENTRY_POINTS = [
    "app.main",
    "app.workers.outbox_dispatcher",
    "app.workers.discovery",
    "app.workers.reports",
    "app.ops.dead_letters",
    "app.ops.metrics",
    "app.events.topics",
]
ML_ONLY_PACKAGES = ["pymupdf", "fitz", "torch", "sentence_transformers"]


@pytest.mark.parametrize("module", API_IMAGE_ENTRY_POINTS)
def test_api_image_entry_point_does_not_need_ml_packages(module: str) -> None:
    """Regression: the report worker imported PyMuPDF through a sentence splitter,
    so the API container (and the public deployment) failed to start."""
    blocked = ", ".join(repr(name) for name in ML_ONLY_PACKAGES)
    code = f"import sys\nfor name in [{blocked}]:\n    sys.modules[name] = None\nimport {module}\n"
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-2000:]
