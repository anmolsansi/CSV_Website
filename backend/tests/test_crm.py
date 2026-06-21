class TestCreateFromRow:
    def test_creates_application_from_row(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        row_id = rows[0]["id"]
        resp = auth_client.post(f"/crm/from-row/{row_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["csv_row_id"] == row_id
        assert data["status"] == "opened"
        assert data["url"]

    def test_returns_404_for_missing_row(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.post("/crm/from-row/99999")
        assert resp.status_code == 404


class TestListApplications:
    def test_returns_paginated_results(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        auth_client.post(f"/crm/from-row/{rows[0]['id']}")
        auth_client.post(f"/crm/from-row/{rows[1]['id']}")
        resp = auth_client.get("/crm/applications")
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "total_count" in data
        assert "statuses" in data
        assert "filter_options" in data
        assert data["total_count"] >= 2

    def test_filter_by_status(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        auth_client.post(f"/crm/from-row/{rows[0]['id']}")
        resp = auth_client.get("/crm/applications", params={"status": "opened"})
        assert resp.status_code == 200
        for app in resp.json()["rows"]:
            assert app["status"] == "opened"

    def test_sort_parameters(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        auth_client.post(f"/crm/from-row/{rows[0]['id']}")
        resp = auth_client.get("/crm/applications", params={"sort_by": "company", "sort_dir": "asc"})
        assert resp.status_code == 200

    def test_pagination_params(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        for r in rows[:5]:
            auth_client.post(f"/crm/from-row/{r['id']}")
        resp = auth_client.get("/crm/applications", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rows"]) <= 2
        assert data["page"] == 1


class TestUpdateApplication:
    def test_update_status(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        app = auth_client.post(f"/crm/from-row/{rows[0]['id']}").json()
        resp = auth_client.patch(f"/crm/applications/{app['id']}", json={"status": "applied"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    def test_update_notes(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        app = auth_client.post(f"/crm/from-row/{rows[0]['id']}").json()
        resp = auth_client.patch(f"/crm/applications/{app['id']}", json={"notes": "Follow up next week"})
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Follow up next week"

    def test_mark_applied(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        app = auth_client.post(f"/crm/from-row/{rows[0]['id']}").json()
        resp = auth_client.patch(f"/crm/applications/{app['id']}", json={"mark_applied": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"
        assert resp.json()["applied_at"] is not None

    def test_update_404_for_invalid_id(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.patch("/crm/applications/99999", json={"status": "applied"})
        assert resp.status_code == 404


class TestBulkUpdate:
    def test_bulk_update_status(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        app1 = auth_client.post(f"/crm/from-row/{rows[0]['id']}").json()
        app2 = auth_client.post(f"/crm/from-row/{rows[1]['id']}").json()
        resp = auth_client.patch("/crm/applications/bulk", json={
            "ids": [app1["id"], app2["id"]],
            "patch": {"status": "interview"},
        })
        assert resp.status_code == 200
        assert resp.json()["updated"] == 2


class TestBulkCreateFromRows:
    def test_bulk_create(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        row_ids = [r["id"] for r in rows[:3]]
        resp = auth_client.post("/crm/from-rows/bulk", json={"row_ids": row_ids})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] + data["updated"] >= 3


class TestAnalytics:
    def test_returns_all_expected_keys(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/analytics")
        assert resp.status_code == 200
        data = resp.json()
        expected_keys = [
            "total_urls", "total_opened", "total_applied",
            "applied_today", "applied_7d",
            "opened_not_applied", "follow_ups_due",
            "interviews", "rejected", "offers",
            "avg_applied_score",
            "by_ats_group", "by_search_bucket", "by_status",
            "daily_applied", "top_companies_opened", "top_companies_applied",
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"

    def test_after_seeding_has_data(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/analytics")
        assert resp.json()["total_urls"] >= 20


class TestFunnelAnalytics:
    def test_returns_stages_and_rates(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/analytics/funnel")
        assert resp.status_code == 200
        data = resp.json()
        assert "stages" in data
        assert "rates" in data
        assert len(data["stages"]) == 6
        stage_names = [s["name"] for s in data["stages"]]
        assert "Uploaded" in stage_names
        assert "Applied" in stage_names
        rates = data["rates"]
        assert "open_rate" in rates
        assert "application_rate" in rates


class TestStats:
    def test_returns_stat_keys(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_opened" in data
        assert "total_applied" in data
        assert "follow_ups_due" in data
        assert "interviews" in data


class TestGoals:
    def test_get_goals_returns_defaults(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/goals")
        assert resp.status_code == 200
        data = resp.json()
        assert "open_per_day" in data
        assert "apply_per_day" in data

    def test_update_goals(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.put("/crm/goals", params={
            "open_per_day": 50,
            "apply_per_day": 20,
            "followup_per_day": 10,
            "applypilot_per_day": 8,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["open_per_day"] == 50
        assert data["apply_per_day"] == 20
        assert data["followup_per_day"] == 10
        assert data["applypilot_per_day"] == 8

    def test_goals_persist(self, auth_client):
        auth_client.post("/test/seed")
        auth_client.put("/crm/goals", params={"open_per_day": 42, "apply_per_day": 7, "followup_per_day": 3, "applypilot_per_day": 2})
        resp = auth_client.get("/crm/goals")
        assert resp.json()["open_per_day"] == 42


class TestGoalProgress:
    def test_returns_goals_and_today(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/analytics/goals")
        assert resp.status_code == 200
        data = resp.json()
        assert "goals" in data
        assert "today" in data
        assert "opened" in data["today"]


class TestSavedViews:
    def test_create_view(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.post("/crm/views", json={
            "name": "My View",
            "view_type": "job_links",
            "filters": {"status": "opened"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My View"
        assert "id" in data

    def test_list_views(self, auth_client):
        auth_client.post("/test/seed")
        auth_client.post("/crm/views", json={"name": "V1", "view_type": "job_links", "filters": {}})
        auth_client.post("/crm/views", json={"name": "V2", "view_type": "job_links", "filters": {}})
        resp = auth_client.get("/crm/views")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_delete_view(self, auth_client):
        auth_client.post("/test/seed")
        view = auth_client.post("/crm/views", json={"name": "Del Me", "view_type": "job_links", "filters": {}}).json()
        resp = auth_client.delete(f"/crm/views/{view['id']}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1

    def test_get_single_view(self, auth_client):
        auth_client.post("/test/seed")
        view = auth_client.post("/crm/views", json={"name": "Single", "view_type": "job_links", "filters": {"q": "test"}}).json()
        resp = auth_client.get(f"/crm/views/{view['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Single"

    def test_toggle_pin(self, auth_client):
        auth_client.post("/test/seed")
        view = auth_client.post("/crm/views", json={"name": "Pinnable", "view_type": "job_links", "filters": {}}).json()
        assert view["is_pinned"] is False
        resp = auth_client.put(f"/crm/views/{view['id']}/pin")
        assert resp.status_code == 200
        assert resp.json()["is_pinned"] is True

    def test_duplicate_view(self, auth_client):
        auth_client.post("/test/seed")
        view = auth_client.post("/crm/views", json={"name": "Original", "view_type": "job_links", "filters": {"x": 1}}).json()
        resp = auth_client.post(f"/crm/views/duplicate/{view['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Original (copy)"
        assert data["filters"] == {"x": 1}

    def test_create_default_views(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.post("/crm/views/defaults")
        assert resp.status_code == 200
        assert resp.json()["created"] >= 1


class TestSessions:
    def test_create_session(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.post("/crm/sessions", json={"name": "Morning search", "notes": "Focus on remote"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Morning search"
        assert "id" in data
        assert data["ended_at"] is None

    def test_list_sessions(self, auth_client):
        auth_client.post("/test/seed")
        auth_client.post("/crm/sessions", json={"name": "S1"})
        auth_client.post("/crm/sessions", json={"name": "S2"})
        resp = auth_client.get("/crm/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_update_session(self, auth_client):
        auth_client.post("/test/seed")
        session = auth_client.post("/crm/sessions", json={"name": "Updatable"}).json()
        resp = auth_client.patch(f"/crm/sessions/{session['id']}", json={"notes": "updated notes"})
        assert resp.status_code == 200
        assert resp.json()["notes"] == "updated notes"

    def test_end_session(self, auth_client):
        auth_client.post("/test/seed")
        session = auth_client.post("/crm/sessions", json={"name": "Ending"}).json()
        resp = auth_client.patch(f"/crm/sessions/{session['id']}", json={"end": True})
        assert resp.status_code == 200
        assert resp.json()["ended_at"] is not None

    def test_delete_session(self, auth_client):
        auth_client.post("/test/seed")
        session = auth_client.post("/crm/sessions", json={"name": "Delete Me"}).json()
        resp = auth_client.delete(f"/crm/sessions/{session['id']}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1

    def test_get_active_session(self, auth_client):
        auth_client.post("/test/seed")
        auth_client.post("/crm/sessions", json={"name": "Active"})
        resp = auth_client.get("/crm/sessions/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["name"] == "Active"
        assert "stats" in data

    def test_active_session_none_when_all_ended(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        session = auth_client.post("/crm/sessions", json={"name": "Done"}).json()
        auth_client.patch(f"/crm/sessions/{session['id']}", json={"end": True})
        resp = auth_client.get("/crm/sessions/active")
        assert resp.status_code == 200
        assert resp.json() is None


class TestExportDashboard:
    def test_csv_export(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/export/dashboard", params={"format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_json_export(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/export/dashboard", params={"format": "json"})
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]


class TestExportApplications:
    def test_csv_export(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        auth_client.post(f"/crm/from-row/{rows[0]['id']}")
        resp = auth_client.get("/crm/export/applications", params={"format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_json_export(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        auth_client.post(f"/crm/from-row/{rows[0]['id']}")
        resp = auth_client.get("/crm/export/applications", params={"format": "json"})
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]


class TestBackupExport:
    def test_backup_returns_json(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/backup/export")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        data = resp.json()
        assert "version" in data
        assert "csv_rows" in data
        assert "job_tracks" in data
        assert "saved_views" in data
        assert "sessions" in data
        assert "audit_events" in data

    def test_backup_includes_seeded_rows(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/backup/export")
        data = resp.json()
        assert len(data["csv_rows"]) >= 20


class TestAuditLog:
    def test_list_audit_events(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/audit")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestFollowUp:
    def test_set_follow_up_preset(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        app = auth_client.post(f"/crm/from-row/{rows[0]['id']}").json()
        resp = auth_client.post(f"/crm/applications/{app['id']}/follow-up", params={"preset": "3_days"})
        assert resp.status_code == 200
        assert resp.json()["follow_up_at"] is not None

    def test_clear_follow_up(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        app = auth_client.post(f"/crm/from-row/{rows[0]['id']}").json()
        auth_client.post(f"/crm/applications/{app['id']}/follow-up", params={"preset": "7_days"})
        resp = auth_client.post(f"/crm/applications/{app['id']}/follow-up", params={"preset": "clear"})
        assert resp.status_code == 200
        assert resp.json()["follow_up_at"] is None

    def test_invalid_preset(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        app = auth_client.post(f"/crm/from-row/{rows[0]['id']}").json()
        resp = auth_client.post(f"/crm/applications/{app['id']}/follow-up", params={"preset": "invalid"})
        assert resp.status_code == 400


class TestMarkDuplicate:
    def test_toggle_duplicate(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        resp = auth_client.post(f"/crm/applications/{rows[0]['id']}/mark-duplicate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate"] is True

    def test_unmark_duplicate(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        auth_client.post(f"/crm/applications/{rows[0]['id']}/mark-duplicate")
        resp = auth_client.post(f"/crm/applications/{rows[0]['id']}/mark-duplicate")
        assert resp.status_code == 200
        assert resp.json()["is_duplicate"] is False

    def test_mark_with_original(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        resp = auth_client.post(
            f"/crm/applications/{rows[1]['id']}/mark-duplicate",
            params={"duplicate_of_id": rows[0]["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate"] is True
        assert data["duplicate_of_id"] == rows[0]["id"]


class TestListDuplicates:
    def test_list_empty_duplicates(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/duplicates")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_marking(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        auth_client.post(f"/crm/applications/{rows[0]['id']}/mark-duplicate")
        resp = auth_client.get("/crm/duplicates")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestAtsAnalytics:
    def test_returns_list(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/analytics/ats")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestBucketAnalytics:
    def test_returns_list(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/analytics/buckets")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestWeeklyReport:
    def test_returns_expected_keys(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/analytics/weekly")
        assert resp.status_code == 200
        data = resp.json()
        assert "uploaded" in data
        assert "opened" in data
        assert "applied" in data
        assert "top_companies" in data
        assert "upcoming_followups" in data


class TestImportExternal:
    def test_import_creates_applications(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.post("/crm/import/external", json=[
            {"url": "https://new-job.com/1", "company": "NewCo", "title": "Dev", "status": "opened"},
            {"url": "https://new-job.com/2", "company": "OtherCo", "title": "PM"},
        ])
        assert resp.status_code == 200
        assert resp.json()["created"] == 2

    def test_import_skips_duplicates(self, auth_client):
        auth_client.post("/test/seed")
        auth_client.post("/crm/import/external", json=[
            {"url": "https://dup.com/1", "company": "DupCo", "title": "Eng"},
        ])
        resp = auth_client.post("/crm/import/external", json=[
            {"url": "https://dup.com/1", "company": "DupCo", "title": "Eng"},
        ])
        assert resp.json()["created"] == 0
