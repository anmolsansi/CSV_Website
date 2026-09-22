import io
import threading
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import (
    DocumentStorageConfigurationError,
    settings,
    validate_document_storage_path,
)
from app.document_schemas import DocumentLinkIn, DocumentUploadMetadata
from app.models import ApplicationDocument, DocumentVersion, JobTrack, User
from app.services import documents as document_service
from app.services.documents import (
    DocumentServiceError,
    create_document,
    link_document,
    stage_upload,
)


def _user(db_session, prefix="documents"):
    user = User(email=f"{prefix}-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


def _track(db_session, user):
    item = JobTrack(
        user_id=user.id,
        url=f"https://example.com/jobs/{uuid4()}",
        company="Example",
        title="Engineer",
    )
    db_session.add(item)
    db_session.flush()
    return item


def _document(db_session, user, *, sha="a" * 64, state="ready"):
    document = DocumentVersion(
        id=str(uuid4()),
        user_id=user.id,
        document_family_id=str(uuid4()),
        kind="resume",
        label="Resume",
        original_filename="resume.pdf",
        media_type="application/pdf",
        size_bytes=12,
        sha256=sha,
        storage_key=f"documents/{user.id}/{uuid4().hex}.bin",
        version_number=1,
        state=state,
    )
    db_session.add(document)
    db_session.flush()
    return document


def test_referenced_version_cannot_be_overwritten(db_session):
    user = _user(db_session)
    track = _track(db_session, user)
    document = _document(db_session, user)
    db_session.add(
        ApplicationDocument(
            user_id=user.id,
            track_id=track.id,
            document_version_id=document.id,
            kind="resume",
            usage="used",
        )
    )
    db_session.flush()

    document.sha256 = "b" * 64
    with pytest.raises(ValueError, match="immutable"):
        db_session.flush()
    db_session.rollback()


def test_cross_user_link_rejected(db_session):
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    document = _document(db_session, owner)
    track = _track(db_session, other)

    with pytest.raises(DocumentServiceError) as exc:
        link_document(
            db_session,
            user_id=other.id,
            track_id=track.id,
            payload=DocumentLinkIn(
                document_version_id=document.id,
                usage="reference",
            ),
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "document_not_found"


def test_ephemeral_or_public_path_configuration_rejected(tmp_path):
    with pytest.raises(DocumentStorageConfigurationError):
        validate_document_storage_path(
            str(tmp_path / "ephemeral"),
            environment="production",
        )

    repo_public = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "frontend"
        / "public"
        / "documents"
    )
    with pytest.raises(DocumentStorageConfigurationError):
        validate_document_storage_path(
            str(repo_public),
            environment="test",
        )


@pytest.mark.postgresql
def test_quota_concurrency_one_reservation_wins(
    engine, tmp_path, monkeypatch
):
    if engine.dialect.name != "postgresql":
        pytest.skip("row-lock quota acceptance requires PostgreSQL")

    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path / "private"))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(document_service, "MAX_ACCOUNT_DOCUMENT_BYTES", 15)

    SetupSession = sessionmaker(bind=engine)
    setup = SetupSession()
    user = User(email=f"quota-{uuid4()}@example.com")
    setup.add(user)
    setup.commit()
    user_id = user.id
    setup.close()

    staged = [
        stage_upload(
            io.BytesIO(b"0123456789"),
            original_filename=f"resume-{index}.txt",
            claimed_media_type="text/plain",
        )
        for index in range(2)
    ]
    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def worker(index):
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            try:
                result = create_document(
                    session,
                    user_id=user_id,
                    metadata=DocumentUploadMetadata(
                        kind="resume",
                        label=f"Resume {index}",
                    ),
                    staged=staged[index],
                    request_key=uuid4(),
                    now=datetime.utcnow(),
                )
                session.commit()
                outcome = ("ready", result.document.id)
            except DocumentServiceError as exc:
                session.rollback()
                outcome = (exc.code, None)
            with lock:
                results.append(outcome)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(value[0] for value in results) == [
        "document_quota_exceeded",
        "ready",
    ]
