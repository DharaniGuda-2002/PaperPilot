"""Import every ORM model so SQLAlchemy can resolve foreign keys between modules.

Every process entry point (API, workers, migrations, ops tools) imports this
once. Without it, a worker that only imports evidence models fails at runtime
with NoReferencedTableError for tables defined elsewhere (found in M5).
"""

from app.core.db import Base
from app.documents import host_schedule as _host_schedule
from app.documents import models as _documents
from app.events import models as _events
from app.evidence import models as _evidence
from app.investigations import models as _investigations
from app.papers import models as _papers

ALL_MODEL_MODULES = (_host_schedule, _documents, _events, _evidence, _investigations, _papers)

__all__ = ["ALL_MODEL_MODULES", "Base"]
