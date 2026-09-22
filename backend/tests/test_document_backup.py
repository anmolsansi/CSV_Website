import io
import zipfile
from uuid import uuid4

import pytest

from app.config import settings
from app.models import CsvRow, DocumentVersion, JobTrack, User
from app.services import backups as backup_service


PDF_BYTES = b"%PDF-1.4\nrecoverable-resume\n%%EOF\n"


@pytest.fixture(autouse=True)
def private_document_storage(tmp_path, monkeypatch):
    root = tmp_path / "private-documents"
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(root))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    return root


def _source_fixture(client, db_session):
    user = db_session.query(User).filter_by(email="test@jobgrid.dev").one()
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=str(uuid4()),
        url=f"https://bundle.example/jobs/{uuid4()}",
        company_guess="Bundle Corp",
        title="Backend Engineer",
    )
    db_session.add(row)
    db_session.flush()
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id,
        url=row.url,
        company="Bundle Corp",
        title="Backend Engineer",
        status="applied",
    )
    db_session.add(track)
    db_session.commit()

    uploaded = client.post(
        "/crm/documents",
        data={"kind": "resume", "label": "Recovery resume"},
        files={"file": ("resume.pdf", PDF_BYTES, "application/pdf")},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    linked = client.post(
        f"/crm/tracks/{track.id}/documents",
        json={"document_version_id": document["id"], "usage": "used"},
    )
    assert linked.status_code == 200, linked.text
    return row.url, document


def _login_destination(client):
    client.post("/auth/logout")
    email = f"bundle-destination-{uuid4()}@example.test"
    response = client.post("/auth/dev-login", json={"email": email})
    assert response.status_code == 200
    return email


def _zip_without(raw: bytes, omitted: str) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(raw), "r")
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            if info.filename != omitted:
                target.writestr(info, source.read(info.filename))
    return output.getvalue()


def _zip_with_extra(raw: bytes, info: zipfile.ZipInfo, payload: bytes = b"x") -> bytes:
    source = zipfile.ZipFile(io.BytesIO(raw), "r")
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for existing in source.infolist():
            target.writestr(existing, source.read(existing.filename))
        target.writestr(info, payload)
    return output.getvalue()


def _corrupt_document_member(raw: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(raw), "r")
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("documents/"):
                payload = payload + b"corrupt"
            target.writestr(info, payload)
    return output.getvalue()


def test_bundle_restores_bytes_and_links(auth_client, db_session):
    source_url, source_document = _source_fixture(auth_client, db_session)
    exported = auth_client.get("/crm/backup/export/bundle")
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("application/zip")

    destination_email = _login_destination(auth_client)
    restored = auth_client.post(
        "/crm/backup/import/bundle?mode=merge_missing",
        files={"file": ("backup.zip", exported.content, "application/zip")},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["document_bytes_included"] is True
    assert restored.json()["counts"]["document_versions"]["created"] == 1
    assert restored.json()["counts"]["application_documents"]["created"] == 1

    destination = db_session.query(User).filter_by(email=destination_email).one()
    document = db_session.query(DocumentVersion).filter_by(
        user_id=destination.id,
        document_family_id=source_document["document_family_id"],
        version_number=1,
    ).one()
    track = db_session.query(JobTrack).filter_by(
        user_id=destination.id,
        url=source_url,
    ).one()

    download = auth_client.get(f"/crm/documents/{document.id}/download")
    assert download.status_code == 200
    assert download.content == PDF_BYTES

    links = auth_client.get(f"/crm/tracks/{track.id}/documents")
    assert links.status_code == 200
    assert links.json()["items"][0]["document"]["id"] == document.id
    assert links.json()["items"][0]["usage"] == "used"


def test_zip_slip_symlink_and_zip_bomb_rejected(
    auth_client, db_session, monkeypatch
):
    _source_fixture(auth_client, db_session)
    exported = auth_client.get("/crm/backup/export/bundle")
    assert exported.status_code == 200

    slip = _zip_with_extra(exported.content, zipfile.ZipInfo("../escape"))
    slip_response = auth_client.post(
        "/crm/backup/import/bundle?mode=verify_only",
        files={"file": ("slip.zip", slip, "application/zip")},
    )
    assert slip_response.status_code == 400
    assert slip_response.json()["detail"]["code"] == "bundle_unsafe_member"

    symlink_info = zipfile.ZipInfo("documents/symlink")
    symlink_info.create_system = 3
    symlink_info.external_attr = (0o120777 << 16)
    symlink = _zip_with_extra(exported.content, symlink_info, b"target")
    symlink_response = auth_client.post(
        "/crm/backup/import/bundle?mode=verify_only",
        files={"file": ("symlink.zip", symlink, "application/zip")},
    )
    assert symlink_response.status_code == 400
    assert symlink_response.json()["detail"]["code"] == "bundle_unsafe_member"

    monkeypatch.setattr(backup_service, "MAX_BACKUP_BUNDLE_EXPANDED_BYTES", 64)
    bomb_response = auth_client.post(
        "/crm/backup/import/bundle?mode=verify_only",
        files={"file": ("bomb.zip", exported.content, "application/zip")},
    )
    assert bomb_response.status_code == 413
    assert bomb_response.json()["detail"]["code"] == "bundle_too_large"


def test_missing_member_fails_before_ready(auth_client, db_session):
    _source_fixture(auth_client, db_session)
    exported = auth_client.get("/crm/backup/export/bundle")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content), "r") as archive:
        member = next(
            info.filename for info in archive.infolist()
            if info.filename.startswith("documents/")
        )
    missing = _zip_without(exported.content, member)

    destination_email = _login_destination(auth_client)
    response = auth_client.post(
        "/crm/backup/import/bundle",
        files={"file": ("missing.zip", missing, "application/zip")},
    )
    assert response.status_code == 400
    destination = db_session.query(User).filter_by(email=destination_email).one()
    assert db_session.query(DocumentVersion).filter_by(
        user_id=destination.id,
        state="ready",
    ).count() == 0


def test_json_only_reports_document_bytes_excluded(auth_client, db_session):
    _source_fixture(auth_client, db_session)
    exported = auth_client.get("/crm/backup/export?version=2")
    assert exported.status_code == 200
    assert exported.json()["document_bytes_included"] is False

    destination_email = _login_destination(auth_client)
    restored = auth_client.post(
        "/crm/backup/import",
        files={"file": ("backup.json", exported.content, "application/json")},
    )
    assert restored.status_code == 200, restored.text
    assert {"code": "document_bytes_excluded"} in restored.json()["warnings"]
    destination = db_session.query(User).filter_by(email=destination_email).one()
    assert db_session.query(DocumentVersion).filter_by(user_id=destination.id).count() == 0


def test_failed_restore_reclaims_staging(
    auth_client, db_session, private_document_storage
):
    _source_fixture(auth_client, db_session)
    exported = auth_client.get("/crm/backup/export/bundle")
    assert exported.status_code == 200
    corrupt = _corrupt_document_member(exported.content)

    _login_destination(auth_client)
    response = auth_client.post(
        "/crm/backup/import/bundle",
        files={"file": ("corrupt.zip", corrupt, "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "bundle_document_checksum_mismatch"
    staging = private_document_storage / "staging"
    assert not staging.exists() or not list(staging.glob("*.part"))
