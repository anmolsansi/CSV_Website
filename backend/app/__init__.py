import hashlib
import os
from urllib.parse import unquote, urlsplit


def _bootstrap_storage_gateway_token() -> None:
    """Derive gateway auth from the existing database credential when needed.

    Render already owns DATABASE_URL and Supabase Edge Functions already own the
    matching database password. Domain-separated hashing avoids introducing a
    second manually managed secret while never sending the raw DB password to
    the storage gateway.
    """
    backend = str(os.getenv("DOCUMENT_STORAGE_BACKEND", "") or "").strip().lower()
    if backend != "gateway" or os.getenv("DOCUMENT_STORAGE_GATEWAY_TOKEN"):
        return

    database_url = str(os.getenv("DATABASE_URL", "") or "").strip()
    if not database_url:
        return
    try:
        password = unquote(urlsplit(database_url).password or "")
    except ValueError:
        return
    if not password:
        return

    token = hashlib.sha256(f"jobgrid-storage-v1:{password}".encode("utf-8")).hexdigest()
    os.environ["DOCUMENT_STORAGE_GATEWAY_TOKEN"] = token


_bootstrap_storage_gateway_token()

# Register additive mapped contracts that extend the core CsvRow/JobTrack models.
# Importing this package must make the version columns and undo journal metadata
# visible to SQLAlchemy metadata, Alembic parity checks, request handlers, and
# maintenance workers before sessions are used.
from . import undo_models as _undo_models  # noqa: E402,F401
