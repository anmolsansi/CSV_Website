import json
from uuid import uuid4

from app.import_models import ImportPreview
from app.models import CsvRow, User


def _auth_user(db):
    user = db.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _preview(auth_client, content: bytes, *, mapping=None, filename="jobs.csv"):
    mapping = mapping or {"0": "url", "1": "title"}
    response = auth_client.post(
        "/crm/imports/preview",
        files={"file": (filename, content, "application/json" if filename.endswith(".json") else "text/csv")},
        data={"mapping": json.dumps(mapping), "options": "{}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_invalid_reject_zero_writes(auth_client, db_session):
    user = _auth_user(db_session)
    before = db_session.query(CsvRow).filter(CsvRow.user_id == user.id).count()
    preview = _preview(
        auth_client,
        b"url,title\nhttps://example.test/import/valid-reject,Valid\nnot-a-url,Bad\n",
    )
    assert preview["counts"] == {
        "create": 1,
        "exact_duplicate": 0,
        "possible_duplicate": 0,
        "invalid": 1,
    }

    response = auth_client.post(
        f"/crm/imports/{preview['preview_id']}/commit",
        json={
            "version": preview["version"],
            "idempotency_key": str(uuid4()),
            "mode": "insert_only",
            "update_fields": [],
            "invalid_policy": "reject",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "invalid_rows_present"
    db_session.expire_all()
    after = db_session.query(CsvRow).filter(CsvRow.user_id == user.id).count()
    assert after == before


def test_skip_invalid_counts_exact(auth_client, db_session):
    user = _auth_user(db_session)
    url = f"https://example.test/import/skip-{uuid4()}"
    preview = _preview(
        auth_client,
        f"url,title\n{url},Valid\ninvalid url,Bad\n".encode(),
    )
    response = auth_client.post(
        f"/crm/imports/{preview['preview_id']}/commit",
        json={
            "version": preview["version"],
            "idempotency_key": str(uuid4()),
            "mode": "insert_only",
            "update_fields": [],
            "invalid_policy": "skip",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["counts"] == {
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "invalid": 1,
    }
    db_session.expire_all()
    stored = db_session.query(CsvRow).filter(CsvRow.user_id == user.id, CsvRow.url == url).one()
    assert stored.title == "Valid"


def test_preview_supports_json_array_objects_and_rejects_other_shape(auth_client):
    url = f"https://example.test/import/json-{uuid4()}"
    preview = _preview(
        auth_client,
        json.dumps([{"url": url, "title": "JSON Engineer"}]).encode(),
        filename="jobs.json",
    )
    assert preview["counts"]["create"] == 1
    assert preview["columns"] == [
        {"index": 0, "label": "url", "mapped_to": "url"},
        {"index": 1, "label": "title", "mapped_to": "title"},
    ]

    response = auth_client.post(
        "/crm/imports/preview",
        files={"file": ("jobs.json", b'{"url":"https://example.test/not-array"}', "application/json")},
        data={"mapping": json.dumps({"0": "url"}), "options": "{}"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_json_shape"


def test_duplicate_headers_are_exposed_by_position(auth_client):
    url = f"https://example.test/import/headers-{uuid4()}"
    preview = _preview(
        auth_client,
        f"url,title,title\n{url},ignored,Chosen\n".encode(),
        mapping={"0": "url", "2": "title"},
    )
    assert [column["label"] for column in preview["columns"]] == ["url", "title", "title"]
    assert [column["index"] for column in preview["columns"]] == [0, 1, 2]
    assert preview["columns"][1]["mapped_to"] is None
    assert preview["columns"][2]["mapped_to"] == "title"
    assert preview["rows"][0]["values"]["title"] == "Chosen"


def test_rejected_csv_preserves_original_values_and_is_spreadsheet_safe(auth_client, db_session):
    preview = _preview(
        auth_client,
        b"url,title\nnot-a-url,=1+1\n",
    )
    assert preview["counts"]["invalid"] == 1

    response = auth_client.get(f"/crm/imports/{preview['preview_id']}/rejected.csv")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    text = response.content.decode("utf-8-sig")
    assert "_source_row,_error_code,url,title" in text
    assert "not-a-url" in text
    assert "'=1+1" in text

    stored = db_session.query(ImportPreview).filter_by(id=preview["preview_id"]).one()
    stored.expires_at = stored.created_at
    db_session.commit()
    expired = auth_client.get(f"/crm/imports/{preview['preview_id']}/rejected.csv")
    assert expired.status_code == 410
    assert expired.json()["detail"]["code"] == "rejected_rows_expired"
