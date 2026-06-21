class TestListRows:
    def test_returns_paginated_structure(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows")
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "columns" in data
        assert "total_count" in data
        assert "page" in data
        assert "page_size" in data
        assert "has_next" in data
        assert "filter_options" in data
        assert "stats" in data

    def test_seeded_data_present(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows")
        data = resp.json()
        assert data["total_count"] >= 20

    def test_row_shape(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows")
        rows = resp.json()["rows"]
        assert len(rows) > 0
        row = rows[0]
        assert "id" in row
        assert "clicked" in row
        assert "data" in row
        assert "app_status" in row
        assert "priority_score" in row
        assert "triage" in row


class TestFilterByAtsGroup:
    def test_filter_greenhouse(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows", params={"ats_group": "greenhouse"})
        assert resp.status_code == 200
        for row in resp.json()["rows"]:
            assert row["data"]["ats_group"].lower() == "greenhouse"

    def test_filter_nonexistent(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows", params={"ats_group": "nonexistent"})
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0


class TestFilterByLocationGroup:
    def test_filter_remote(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows", params={"location_group": "remote"})
        assert resp.status_code == 200
        for row in resp.json()["rows"]:
            assert row["data"]["location_group"].lower() == "remote"


class TestFilterBySearchBucket:
    def test_filter_ai(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows", params={"search_bucket": "ai"})
        assert resp.status_code == 200
        for row in resp.json()["rows"]:
            assert row["data"]["search_bucket"].lower() == "ai"


class TestSortParameters:
    def test_sort_by_title_asc(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows", params={"sort_by": "title", "sort_dir": "asc"})
        assert resp.status_code == 200

    def test_sort_by_created_at_desc(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows", params={"sort_by": "created_at", "sort_dir": "desc"})
        assert resp.status_code == 200
        rows = resp.json()["rows"]
        if len(rows) >= 2:
            assert rows[0]["id"] >= rows[1]["id"]


class TestSearchQuery:
    def test_search_by_company(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows", params={"q": "Acme"})
        assert resp.status_code == 200
        for row in resp.json()["rows"]:
            assert "acme" in row["data"]["company_guess"].lower()


class TestPagination:
    def test_page_size_limits(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows", params={"page_size": 5, "page": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rows"]) <= 5

    def test_second_page(self, auth_client):
        auth_client.post("/test/seed")
        resp1 = auth_client.get("/rows", params={"page": 1, "page_size": 5})
        resp2 = auth_client.get("/rows", params={"page": 2, "page_size": 5})
        assert resp2.status_code == 200
        if resp1.json()["has_next"]:
            ids1 = [r["id"] for r in resp1.json()["rows"]]
            ids2 = [r["id"] for r in resp2.json()["rows"]]
            assert len(set(ids1) & set(ids2)) == 0


class TestDeleteRows:
    def test_delete_rows(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        row_ids = [rows[0]["id"], rows[1]["id"]]
        resp = auth_client.request("DELETE", "/rows", content='{"row_ids": ' + str(row_ids) + ', "mode": "delete"}', headers={"content-type": "application/json"})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    def test_archive_rows(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        row_ids = [rows[0]["id"]]
        resp = auth_client.request("DELETE", "/rows", content='{"row_ids": ' + str(row_ids) + ', "mode": "archive"}', headers={"content-type": "application/json"})
        assert resp.status_code == 200
        assert resp.json()["archived"] == 1

    def test_delete_empty_list(self, auth_client):
        auth_client.post("/test/reset")
        auth_client.post("/test/seed")
        resp = auth_client.request("DELETE", "/rows", content='{"row_ids": [], "mode": "delete"}', headers={"content-type": "application/json"})
        assert resp.status_code == 400


class TestClickTracking:
    def test_record_click(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        row_id = rows[0]["id"]
        resp = auth_client.post(f"/rows/{row_id}/click")
        assert resp.status_code == 200
        data = resp.json()
        assert data["clicked"] is True
        assert data["clicked_at"] is not None

    def test_click_idempotent(self, auth_client):
        auth_client.post("/test/seed")
        rows = auth_client.get("/rows").json()["rows"]
        row_id = rows[0]["id"]
        auth_client.post(f"/rows/{row_id}/click")
        resp = auth_client.post(f"/rows/{row_id}/click")
        assert resp.status_code == 200
        assert resp.json()["clicked"] is True


class TestPreferences:
    def test_get_default_preferences(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert "hidden_columns" in data
        assert "column_order" in data

    def test_set_preferences(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.put("/preferences", json={
            "hidden_columns": ["jd_text", "error"],
            "column_order": ["url", "company_guess", "title"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "jd_text" in data["hidden_columns"]
        assert data["column_order"] == ["url", "company_guess", "title"]

    def test_preferences_persist(self, auth_client):
        auth_client.post("/test/seed")
        auth_client.put("/preferences", json={"hidden_columns": ["url"], "column_order": ["title"]})
        resp = auth_client.get("/preferences")
        assert "url" in resp.json()["hidden_columns"]
