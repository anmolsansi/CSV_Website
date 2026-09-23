import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.import_models import ImportMapping
from app.import_schemas import ImportCommitRequest, ImportContractError, header_fingerprint
from app.models import CsvRow, User
from app.services.import_backups import (
    export_backup_v2_with_import_mappings,
    restore_backup_payload_with_import_mappings,
)
from app.services.import_mapping import mapping_for_headers
from app.services.imports import commit_import_preview, create_import_preview, parse_import_source


def _user(db, prefix):
    user = User(email=f"{prefix}-{uuid4()}@example.test", timezone="UTC")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _preview(db, user, content: bytes, *, filename="jobs.csv", mapping=None):
    preview = create_import_preview(
        db,
        user_id=user.id,
        raw=content,
        filename=filename,
        content_type="application/json" if filename.endswith(".json") else "text/csv",
        mapping_value=mapping or {"0": "url", "1": "title"},
    )
    db.commit()
    db.refresh(preview)
    return preview


def test_parser_fixture_matrix_expected_values():
    headers, rows = parse_import_source(
        b"\xef\xbb\xbfurl,title,notes\r\nhttps://example.test/a,\"Platform, Engineer\",\"line one\nline two\"\r\n",
        filename="bom.csv",
        content_type="text/csv",
    )
    assert headers == ["url", "title", "notes"]
    assert rows == [(2, ["https://example.test/a", "Platform, Engineer", "line one\nline two"])]

    duplicate_headers, duplicate_rows = parse_import_source(
        b"url,title,title,company_guess\nhttps://example.test/b,first,second,\n",
        filename="duplicate.csv",
        content_type="text/csv",
    )
    assert duplicate_headers == ["url", "title", "title", "company_guess"]
    assert duplicate_rows == [(2, ["https://example.test/b", "first", "second", ""])]

    json_headers, json_rows = parse_import_source(
        b'[{"url":"https://example.test/c","title":"Engineer"},{"url":"https://example.test/d","company_guess":null}]',
        filename="jobs.json",
        content_type="application/json",
    )
    assert json_headers == ["url", "title", "company_guess"]
    assert json_rows == [
        (1, ["https://example.test/c", "Engineer", None]),
        (2, ["https://example.test/d", None, None]),
    ]

    with pytest.raises(ImportContractError) as malformed:
        parse_import_source(
            b'[{"url":"https://example.test/broken",}]',
            filename="broken.json",
            content_type="application/json",
        )
    assert malformed.value.code == "invalid_json"


def test_over_limit_zero_destination_writes(db_session):
    user = _user(db_session, "jg060-limits")
    before = db_session.query(CsvRow).filter_by(user_id=user.id).count()

    maximum = "url,title\n" + "".join(
        f"https://example.test/max/{index},Engineer {index}\n" for index in range(2000)
    )
    headers, rows = parse_import_source(
        maximum.encode(), filename="maximum.csv", content_type="text/csv"
    )
    assert headers == ["url", "title"]
    assert len(rows) == 2000

    over_records = "url,title\n" + "".join(
        f"https://example.test/over/{index},Engineer {index}\n" for index in range(2001)
    )
    with pytest.raises(ImportContractError) as record_error:
        create_import_preview(
            db_session,
            user_id=user.id,
            raw=over_records.encode(),
            filename="over.csv",
            content_type="text/csv",
            mapping_value={"0": "url", "1": "title"},
        )
    assert record_error.value.code == "too_many_records"
    db_session.rollback()

    with pytest.raises(ImportContractError) as byte_error:
        create_import_preview(
            db_session,
            user_id=user.id,
            raw=b"x" * ((10 * 1024 * 1024) + 1),
            filename="too-large.csv",
            content_type="text/csv",
            mapping_value={"0": "url"},
        )
    assert byte_error.value.code == "import_too_large"
    db_session.rollback()

    assert db_session.query(CsvRow).filter_by(user_id=user.id).count() == before


def test_concurrent_commit_no_lost_updates(db_session, engine):
    user = _user(db_session, "jg060-concurrent")
    first = _preview(
        db_session,
        user,
        b"url,title\nhttps://example.test/concurrent/a,First\n",
    )
    second = _preview(
        db_session,
        user,
        b"url,title\nhttps://example.test/concurrent/b,Second\n",
    )
    # Both previews intentionally describe the same original destination state.
    second.destination_fingerprint = first.destination_fingerprint
    db_session.commit()

    barrier = Barrier(2)
    Session = sessionmaker(bind=engine)

    def worker(preview_id, version):
        session = Session()
        try:
            payload = ImportCommitRequest(
                version=version,
                idempotency_key=str(uuid4()),
                mode="insert_only",
                update_fields=[],
                invalid_policy="reject",
            )
            barrier.wait(timeout=10)
            try:
                result, replayed = commit_import_preview(
                    session,
                    user_id=user.id,
                    preview_id=preview_id,
                    payload=payload,
                )
                session.commit()
                return ("success", result["counts"], replayed)
            except ImportContractError as exc:
                session.rollback()
                return (exc.code, None, False)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(
            lambda args: worker(*args),
            [(first.id, first.version), (second.id, second.version)],
        ))

    codes = sorted(item[0] for item in outcomes)
    assert codes == ["destination_changed", "success"]
    success = next(item for item in outcomes if item[0] == "success")
    assert success[1] == {"created": 1, "updated": 0, "skipped": 0, "invalid": 0}

    db_session.expire_all()
    stored = db_session.query(CsvRow).filter(
        CsvRow.user_id == user.id,
        CsvRow.url.in_([
            "https://example.test/concurrent/a",
            "https://example.test/concurrent/b",
        ]),
    ).all()
    assert len(stored) == 1


def test_saved_mapping_header_mismatch_not_silent(db_session):
    owner = _user(db_session, "jg060-mapping-owner")
    headers = ["url", "title"]
    mapping = ImportMapping(
        user_id=owner.id,
        name="Standard ATS export",
        header_fingerprint=header_fingerprint(headers),
        mapping_json={"0": "url", "1": "title"},
        version=1,
    )
    db_session.add(mapping)
    db_session.commit()

    backup = export_backup_v2_with_import_mappings(db_session, owner.id)
    assert backup["f9_import_mappings"]["mappings"][0]["name"] == "Standard ATS export"

    restored_user = _user(db_session, "jg060-mapping-restored")
    result = restore_backup_payload_with_import_mappings(
        db_session,
        restored_user.id,
        json.dumps(backup).encode("utf-8"),
        "merge_missing",
    )
    assert result["counts"]["import_mappings"] == {"created": 1, "existing": 0}

    restored = db_session.query(ImportMapping).filter_by(
        user_id=restored_user.id,
        name="Standard ATS export",
    ).one()
    assert mapping_for_headers(restored, headers) == {"0": "url", "1": "title"}

    with pytest.raises(ImportContractError) as mismatch:
        mapping_for_headers(restored, ["title", "url"])
    assert mismatch.value.code == "saved_mapping_header_mismatch"
    assert mismatch.value.status_code == 409


def test_spreadsheet_error_report_formula_safe(auth_client):
    response = auth_client.post(
        "/crm/imports/preview",
        files={"file": ("formula.csv", b"url,title\nnot-a-url,=HYPERLINK(\"https://evil.test\")\n", "text/csv")},
        data={"mapping": json.dumps({"0": "url", "1": "title"}), "options": "{}"},
    )
    assert response.status_code == 201, response.text
    preview = response.json()
    assert preview["counts"]["invalid"] == 1

    rejected = auth_client.get(f"/crm/imports/{preview['preview_id']}/rejected.csv")
    assert rejected.status_code == 200
    text = rejected.content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text
    assert "=HYPERLINK" in text
    assert rejected.headers["cache-control"] == "no-store"


def test_maximum_fixture_records_actual_counts_queries_and_runtime(db_session, engine, capsys):
    user = _user(db_session, "jg060-max-fixture")
    content = "url,title\n" + "".join(
        f"https://example.test/measured/{index},Engineer {index}\n" for index in range(2000)
    )
    query_count = 0

    def count_query(*_args, **_kwargs):
        nonlocal query_count
        query_count += 1

    event.listen(engine, "before_cursor_execute", count_query)
    started = perf_counter()
    try:
        preview = create_import_preview(
            db_session,
            user_id=user.id,
            raw=content.encode(),
            filename="maximum.csv",
            content_type="text/csv",
            mapping_value={"0": "url", "1": "title"},
        )
        db_session.flush()
        assert preview.summary_json["record_count"] == 2000
        assert preview.summary_json["counts"] == {
            "create": 2000,
            "exact_duplicate": 0,
            "possible_duplicate": 0,
            "invalid": 0,
        }
        payload = ImportCommitRequest(
            version=preview.version,
            idempotency_key=str(uuid4()),
            mode="insert_only",
            update_fields=[],
            invalid_policy="reject",
        )
        result, replayed = commit_import_preview(
            db_session,
            user_id=user.id,
            preview_id=preview.id,
            payload=payload,
        )
        db_session.commit()
    finally:
        event.remove(engine, "before_cursor_execute", count_query)

    elapsed_ms = int((perf_counter() - started) * 1000)
    assert replayed is False
    assert result["counts"] == {"created": 2000, "updated": 0, "skipped": 0, "invalid": 0}
    assert db_session.query(CsvRow).filter_by(user_id=user.id).count() == 2000
    assert query_count > 0
    print(f"JG060_MAX_FIXTURE records=2000 created=2000 queries={query_count} elapsed_ms={elapsed_ms}")
    captured = capsys.readouterr().out
    assert "JG060_MAX_FIXTURE records=2000 created=2000 queries=" in captured
