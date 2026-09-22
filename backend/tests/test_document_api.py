import hashlib
from uuid import uuid4

import pytest

from app.config import settings
from app.models import JobTrack, User


PDF_V1 = b"%PDF-1.4\nresume-version-one\n%%EOF\n"
PDF_V2 = b"%PDF-1.4\nresume-version-two\n%%EOF\n"


@pytest.fixture(autouse=True)
def private_document_storage(tmp_path, monkeypatch):
    root = tmp_path / "private-documents"
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(root))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    return root


def _upload(
    client,
    *,
    content=PDF_V1,
    filename="resume.pdf",
    label=None,
    kind="resume",
    family_id=None,
    request_key=None,
):
    label = label or f"Resume {uuid4()}"
    data = {"kind": kind, "label": label}
    if family_id:
        data["document_family_id"] = family_id
    return client.post(
        "/crm/documents",
        data=data,
        files={"file": (filename, content, "application/pdf")},
        headers={"Idempotency-Key": str(request_key or uuid4())},
    )


def _track(db_session, email="test@jobgrid.dev"):
    user = db_session.query(User).filter(User.email == email).one()
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.com/application/{uuid4()}",
        company="Example Corp",
        title="Software Engineer",
    )
    db_session.add(track)
    db_session.commit()
    return track


def test_download_headers_and_hash_match(auth_client):
    response = _upload(auth_client, content=PDF_V1, filename="../../resume.pdf")
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["sha256"] == hashlib.sha256(PDF_V1).hexdigest()
    assert document["original_filename"] == "resume.pdf"
    assert "storage_key" not in document

    download = auth_client.get(f"/crm/documents/{document['id']}/download")
    assert download.status_code == 200
    assert download.content == PDF_V1
    assert download.headers["cache-control"] == "private, no-store"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in download.headers["content-disposition"].lower()
    assert ".." not in download.headers["content-disposition"]


def test_retry_upload_single_version(auth_client):
    key = uuid4()
    label = f"Idempotent {uuid4()}"
    first = _upload(auth_client, label=label, request_key=key)
    second = _upload(auth_client, label=label, request_key=key)
    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]

    listing = auth_client.get("/crm/documents")
    assert listing.status_code == 200
    matching = [item for item in listing.json()["items"] if item["label"] == label]
    assert len(matching) == 1
    assert matching[0]["version_number"] == 1


def test_foreign_uuid_download404(auth_client):
    response = _upload(auth_client)
    assert response.status_code == 201
    document_id = response.json()["id"]

    auth_client.post("/auth/logout")
    login = auth_client.post("/auth/dev-login", json={"email": f"other-{uuid4()}@example.com"})
    assert login.status_code == 200
    foreign = auth_client.get(f"/crm/documents/{document_id}/download")
    assert foreign.status_code == 404
    assert foreign.json()["detail"]["code"] == "document_not_found"


def test_download_requires_current_session(auth_client):
    response = _upload(auth_client)
    assert response.status_code == 201
    document_id = response.json()["id"]

    auth_client.post("/auth/logout")
    unauthenticated = auth_client.get(f"/crm/documents/{document_id}/download")
    assert unauthenticated.status_code in {401, 403}


def test_failed_upload_never_appears_ready(auth_client):
    label = f"Bad upload {uuid4()}"
    response = auth_client.post(
        "/crm/documents",
        data={"kind": "resume", "label": label},
        files={"file": ("resume.bin", b"\xff\xfe\xfd", "application/octet-stream")},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 415

    listing = auth_client.get("/crm/documents")
    assert listing.status_code == 200
    assert not any(
        item["label"] == label and item["state"] == "ready"
        for item in listing.json()["items"]
    )


def test_referenced_delete_conflict_explained(auth_client, db_session):
    document_response = _upload(auth_client)
    assert document_response.status_code == 201
    document = document_response.json()
    track = _track(db_session)

    linked = auth_client.post(
        f"/crm/tracks/{track.id}/documents",
        json={"document_version_id": document["id"], "usage": "reference"},
    )
    assert linked.status_code == 200, linked.text

    deleted = auth_client.delete(f"/crm/documents/{document['id']}")
    assert deleted.status_code == 409
    detail = deleted.json()["detail"]
    assert detail["code"] == "document_is_referenced"
    assert detail["applications"][0]["track_id"] == track.id
    assert detail["applications"][0]["usage"] == "reference"


def test_application_A_keeps_v1_after_v2(auth_client, db_session):
    v1_response = _upload(auth_client, content=PDF_V1, label=f"Resume family {uuid4()}")
    assert v1_response.status_code == 201, v1_response.text
    v1 = v1_response.json()

    app_a = _track(db_session)
    attach_a = auth_client.post(
        f"/crm/tracks/{app_a.id}/documents",
        json={"document_version_id": v1["id"], "usage": "used"},
    )
    assert attach_a.status_code == 200, attach_a.text

    v2_response = _upload(
        auth_client,
        content=PDF_V2,
        label=v1["label"],
        family_id=v1["document_family_id"],
    )
    assert v2_response.status_code == 201, v2_response.text
    v2 = v2_response.json()
    assert v2["version_number"] == 2

    app_b = _track(db_session)
    attach_b = auth_client.post(
        f"/crm/tracks/{app_b.id}/documents",
        json={"document_version_id": v2["id"], "usage": "used"},
    )
    assert attach_b.status_code == 200, attach_b.text

    a_documents = auth_client.get(f"/crm/tracks/{app_a.id}/documents")
    b_documents = auth_client.get(f"/crm/tracks/{app_b.id}/documents")
    assert a_documents.status_code == 200
    assert b_documents.status_code == 200
    assert a_documents.json()["items"][0]["document"]["id"] == v1["id"]
    assert a_documents.json()["items"][0]["document"]["sha256"] == hashlib.sha256(PDF_V1).hexdigest()
    assert b_documents.json()["items"][0]["document"]["id"] == v2["id"]

    v1_download = auth_client.get(f"/crm/documents/{v1['id']}/download")
    assert v1_download.content == PDF_V1
