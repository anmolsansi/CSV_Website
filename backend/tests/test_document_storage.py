import hashlib
import io
import os
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.config import settings
from app.document_schemas import MAX_DOCUMENT_BYTES
from app.models import DocumentVersion, User
from app.services.documents import (
    DocumentServiceError,
    reconcile_document_storage,
    safe_display_filename,
    stage_upload,
)


@pytest.fixture()
def private_storage(tmp_path, monkeypatch):
    root = tmp_path / "jobgrid-private-documents"
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(root))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    return root


def test_oversize_stream_stops_without_ready_file(private_storage):
    payload = b"x" * (MAX_DOCUMENT_BYTES + 1)
    with pytest.raises(DocumentServiceError) as exc:
        stage_upload(
            io.BytesIO(payload),
            original_filename="too-large.txt",
            claimed_media_type="text/plain",
        )
    assert exc.value.code == "document_too_large"
    assert list((private_storage / "staging").glob("*.part")) == []
    assert list((private_storage / "documents").rglob("*.bin")) == []


def test_filename_path_traversal_cannot_escape_storage(private_storage):
    staged = stage_upload(
        io.BytesIO(b"plain text resume"),
        original_filename="../../../../public/evil.txt",
        claimed_media_type="text/plain",
    )
    assert staged.original_filename == "evil.txt"
    assert private_storage.resolve() in staged.path.resolve().parents
    assert "public" not in staged.path.parts
    assert safe_display_filename(r"..\\..\\resume.pdf") == "resume.pdf"


def test_crash_before_and_after_rename_reconciles(
    db_session, private_storage
):
    user = User(email=f"reconcile-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    old = datetime.utcnow() - timedelta(hours=2)
    bytes_ready = b"published-before-db-ready"
    ready_key = f"documents/{user.id}/{uuid4().hex}.bin"
    pending_ready = DocumentVersion(
        id=str(uuid4()),
        user_id=user.id,
        document_family_id=str(uuid4()),
        kind="resume",
        label="Resume A",
        original_filename="a.txt",
        media_type="text/plain",
        size_bytes=len(bytes_ready),
        sha256=hashlib.sha256(bytes_ready).hexdigest(),
        storage_key=ready_key,
        version_number=1,
        created_at=old,
        state="pending",
    )
    pending_missing = DocumentVersion(
        id=str(uuid4()),
        user_id=user.id,
        document_family_id=str(uuid4()),
        kind="cover_letter",
        label="Cover letter",
        original_filename="cover.txt",
        media_type="text/plain",
        size_bytes=5,
        sha256=hashlib.sha256(b"cover").hexdigest(),
        storage_key=f"documents/{user.id}/{uuid4().hex}.bin",
        version_number=1,
        created_at=old,
        state="pending",
    )
    db_session.add_all([pending_ready, pending_missing])
    db_session.flush()

    ready_path = private_storage / ready_key
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.write_bytes(bytes_ready)

    staging = private_storage / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    stale_stage = staging / "stale.part"
    stale_stage.write_bytes(b"partial")

    orphan = private_storage / "documents" / "999999" / "orphan.bin"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")

    old_epoch = old.timestamp()
    os.utime(stale_stage, (old_epoch, old_epoch))
    os.utime(orphan, (old_epoch, old_epoch))

    counters = reconcile_document_storage(
        db_session,
        now=datetime.utcnow(),
        limit=100,
    )

    assert pending_ready.state == "ready"
    assert pending_missing.state == "failed"
    assert counters["pending_ready"] >= 1
    assert counters["pending_failed"] >= 1
    assert counters["staging_removed"] >= 1
    assert counters["orphan_removed"] >= 1
    assert not stale_stage.exists()
    assert not orphan.exists()
