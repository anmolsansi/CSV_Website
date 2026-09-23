# Register additive mapped contracts that extend the core CsvRow/JobTrack models.
# Importing this package must make the version columns and undo journal metadata
# visible to SQLAlchemy metadata, Alembic parity checks, request handlers, and
# maintenance workers before sessions are used.
from . import undo_models as _undo_models  # noqa: F401
