import csv
import io
from datetime import datetime

from sqlalchemy.orm import sessionmaker

from app.models import CsvRow, JobTrack, User


def _login(client, email):
    response = client.post("/auth/dev-login", json={"email": email})
    assert response.status_code == 200


def _session(engine):
    return sessionmaker(bind=engine)()


def _row(db, user, suffix, **values):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"jg006-{suffix}",
        url=values.pop("url", f"https://jobs.example/{suffix}"),
        **values,
    )
    db.add(row)
    db.flush()
    return row


def _track(db, user, row, suffix, **values):
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id if row else None,
        url=values.pop("url", row.url if row else f"https://jobs.example/app/{suffix}"),
        opened_at=values.pop("opened_at", datetime(2026, 9, 1, 12, 0, 0)),
        **values,
    )
    db.add(track)
    db.flush()
    return track


def test_filtered_export_equals_all_list_pages(client, engine):
    email = "jg006-parity@jobgrid.test"
    _login(client, email)

    db = _session(engine)
    try:
        user = db.query(User).filter_by(email=email).one()
        expected_urls = []
        for index in range(61):
            row = _row(
                db,
                user,
                f"match-{index}",
                title=f"Engineer {index:03d}",
                company_guess="Acme",
                ats_group="greenhouse",
                location_group="remote",
                search_bucket="backend",
                decision="keep",
                sponsorship_status="positive",
                fit_category="strong",
                seniority_level="senior",
                work_model_extracted="remote",
                role_family="software",
                salary_min_extracted="150000",
                salary_max_extracted="220000",
                clicked=False,
                jd_text_length="500",
            )
            expected_urls.append(row.url)
        _row(
            db,
            user,
            "control-onsite",
            title="Engineer onsite",
            company_guess="Acme",
            ats_group="greenhouse",
            location_group="onsite",
            search_bucket="backend",
            decision="keep",
            sponsorship_status="positive",
        )
        _row(
            db,
            user,
            "control-sponsorship",
            title="Engineer remote negative",
            company_guess="Acme",
            ats_group="greenhouse",
            location_group="remote",
            search_bucket="backend",
            decision="keep",
            sponsorship_status="negative",
        )
        db.commit()
    finally:
        db.close()

    filters = {
        "location_group": "remote",
        "search_bucket": "backend",
        "decision": "keep",
        "sponsorship_status": "positive",
        "q": "Engineer",
        "sort_by": "title",
        "sort_dir": "asc",
    }
    list_urls = []
    page = 1
    while True:
        response = client.get("/rows", params={**filters, "page": page, "page_size": 25})
        assert response.status_code == 200
        payload = response.json()
        list_urls.extend(item["data"]["url"] for item in payload["rows"])
        if not payload["has_next"]:
            break
        page += 1

    export = client.get(
        "/crm/export/dashboard",
        params={"format": "json", "scope": "filtered", **filters},
    )
    assert export.status_code == 200
    export_urls = [item["url"] for item in export.json()]

    assert len(list_urls) == 61
    assert len(export_urls) == 61
    assert export_urls == list_urls
    assert export_urls == expected_urls
    assert "https://jobs.example/control-onsite" not in export_urls
    assert "https://jobs.example/control-sponsorship" not in export_urls


def test_selected_empty_never_exports_all(client, engine):
    email = "jg006-empty-selected@jobgrid.test"
    _login(client, email)
    db = _session(engine)
    try:
        user = db.query(User).filter_by(email=email).one()
        _row(db, user, "safe-existing", title="Existing")
        db.commit()
    finally:
        db.close()

    empty = client.get(
        "/crm/export/dashboard",
        params={"format": "json", "scope": "selected", "row_ids": ""},
    )
    assert empty.status_code == 422
    assert "attachment" not in empty.headers.get("content-disposition", "")

    malformed = client.get(
        "/crm/export/dashboard",
        params={"format": "json", "scope": "selected", "row_ids": "not-an-id"},
    )
    assert malformed.status_code == 422
    assert "attachment" not in malformed.headers.get("content-disposition", "")


def test_selected_foreign_id(client, engine):
    owner_email = "jg006-owner@jobgrid.test"
    foreign_email = "jg006-foreign@jobgrid.test"
    _login(client, owner_email)

    db = _session(engine)
    try:
        owner = db.query(User).filter_by(email=owner_email).one()
        foreign = User(email=foreign_email)
        db.add(foreign)
        db.flush()
        own_row = _row(db, owner, "owned", title="Owned")
        foreign_row = _row(db, foreign, "foreign", title="Foreign")
        db.commit()
        own_id = own_row.id
        foreign_id = foreign_row.id
    finally:
        db.close()

    response = client.get(
        "/crm/export/dashboard",
        params={
            "format": "json",
            "scope": "selected",
            "row_ids": f"{own_id},{foreign_id}",
        },
    )
    assert response.status_code == 404
    assert "attachment" not in response.headers.get("content-disposition", "")


def test_formula_cells_escaped_in_csv_only(client, engine):
    email = "jg006-formula@jobgrid.test"
    _login(client, email)
    original_title = '=HYPERLINK("https://evil.test","click")'
    original_company = "\t+SUM(1,1)"

    db = _session(engine)
    try:
        user = db.query(User).filter_by(email=email).one()
        row = _row(
            db,
            user,
            "formula",
            title=original_title,
            company_guess=original_company,
        )
        db.commit()
        row_id = row.id
    finally:
        db.close()

    common = {
        "scope": "selected",
        "row_ids": str(row_id),
        "columns": "title,company_guess",
    }
    json_response = client.get(
        "/crm/export/dashboard",
        params={**common, "format": "json"},
    )
    assert json_response.status_code == 200
    json_row = json_response.json()[0]
    assert json_row["title"] == original_title
    assert json_row["company_guess"] == original_company

    csv_response = client.get(
        "/crm/export/dashboard",
        params={**common, "format": "csv"},
    )
    assert csv_response.status_code == 200
    reader = csv.DictReader(io.StringIO(csv_response.text))
    assert reader.fieldnames == ["title", "company_guess", "clicked", "clicked_at"]
    csv_row = next(reader)
    assert csv_row["title"] == "'" + original_title
    assert csv_row["company_guess"] == "'" + original_company

    db = _session(engine)
    try:
        stored = db.query(CsvRow).filter_by(id=row_id).one()
        assert stored.title == original_title
        assert stored.company_guess == original_company
    finally:
        db.close()


def test_unknown_dashboard_column_is_rejected(client, engine):
    email = "jg006-column@jobgrid.test"
    _login(client, email)
    response = client.get(
        "/crm/export/dashboard",
        params={"format": "json", "columns": "title,not_a_real_column"},
    )
    assert response.status_code == 400
    assert "attachment" not in response.headers.get("content-disposition", "")


def test_application_export_uses_shared_filters_and_order(client, engine):
    email = "jg006-apps@jobgrid.test"
    _login(client, email)
    db = _session(engine)
    try:
        user = db.query(User).filter_by(email=email).one()
        first_row = _row(
            db,
            user,
            "app-first",
            title="Backend A",
            company_guess="Acme",
            location_group="remote",
            decision="keep",
            sponsorship_status="positive",
        )
        second_row = _row(
            db,
            user,
            "app-second",
            title="Backend B",
            company_guess="Acme",
            location_group="remote",
            decision="keep",
            sponsorship_status="positive",
        )
        control_row = _row(
            db,
            user,
            "app-control",
            title="Backend C",
            company_guess="Acme",
            location_group="onsite",
            decision="keep",
            sponsorship_status="positive",
        )
        first = _track(
            db,
            user,
            first_row,
            "app-first",
            company="Acme",
            title="Backend A",
            ats_group="greenhouse",
            search_bucket="backend",
            status="opened",
            opened_at=datetime(2026, 9, 1, 9, 0, 0),
        )
        second = _track(
            db,
            user,
            second_row,
            "app-second",
            company="Acme",
            title="Backend B",
            ats_group="greenhouse",
            search_bucket="backend",
            status="opened",
            opened_at=datetime(2026, 9, 2, 9, 0, 0),
        )
        _track(
            db,
            user,
            control_row,
            "app-control",
            company="Acme",
            title="Backend C",
            ats_group="greenhouse",
            search_bucket="backend",
            status="opened",
            opened_at=datetime(2026, 9, 3, 9, 0, 0),
        )
        db.commit()
        expected_urls = [first.url, second.url]
    finally:
        db.close()

    response = client.get(
        "/crm/export/applications",
        params={
            "format": "json",
            "scope": "filtered",
            "status": "opened",
            "ats_group": "greenhouse",
            "search_bucket": "backend",
            "location_group": "remote",
            "decision": "keep",
            "sponsorship_status": "positive",
            "sort_by": "opened_at",
            "sort_dir": "asc",
        },
    )
    assert response.status_code == 200
    assert [item["url"] for item in response.json()] == expected_urls


def test_application_selected_scope_rejects_foreign_track(client, engine):
    owner_email = "jg006-app-owner@jobgrid.test"
    foreign_email = "jg006-app-foreign@jobgrid.test"
    _login(client, owner_email)
    db = _session(engine)
    try:
        owner = db.query(User).filter_by(email=owner_email).one()
        foreign = User(email=foreign_email)
        db.add(foreign)
        db.flush()
        owner_row = _row(db, owner, "app-owned-row", title="Owned")
        foreign_row = _row(db, foreign, "app-foreign-row", title="Foreign")
        owner_track = _track(db, owner, owner_row, "app-owned-track", status="opened")
        foreign_track = _track(db, foreign, foreign_row, "app-foreign-track", status="opened")
        db.commit()
        owner_track_id = owner_track.id
        foreign_track_id = foreign_track.id
    finally:
        db.close()

    response = client.get(
        "/crm/export/applications",
        params={
            "format": "json",
            "scope": "selected",
            "row_ids": f"{owner_track_id},{foreign_track_id}",
        },
    )
    assert response.status_code == 404
    assert "attachment" not in response.headers.get("content-disposition", "")
