class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestDevLogin:
    def test_dev_login_creates_user(self, client):
        resp = client.post("/auth/dev-login", json={"email": "newuser@test.dev"})
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["email"] == "newuser@test.dev"

    def test_dev_login_existing_user(self, client):
        resp1 = client.post("/auth/dev-login", json={"email": "existing@test.dev"})
        resp2 = client.post("/auth/dev-login", json={"email": "existing@test.dev"})
        assert resp1.json()["id"] == resp2.json()["id"]


class TestUpload:
    def test_upload_csv(self, auth_client):
        csv_content = b"url,company,title\nhttps://example.com/job/1,Acme,Engineer\nhttps://example.com/job/2,TechCorp,Designer\n"
        resp = auth_client.post(
            "/upload",
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "batch_id" in data
        assert "inserted" in data
        assert data["required_columns"] == ["url"]

    def test_upload_url_only_csv_is_valid(self, auth_client):
        csv_content = b"url\nhttps://minimal.example.com/job/1\n"
        resp = auth_client.post(
            "/upload",
            files={"file": ("minimal.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 1
        assert data["missing_required_columns"] == []
        assert "missing_optional_columns" in data
        assert "title" in data["missing_optional_columns"]

    def test_upload_csv_with_duplicate_urls(self, auth_client):
        csv_content = (
            b"url,company,title\n"
            b"https://dup.com/job/1,Acme,Engineer\n"
            b"https://dup.com/job/1,Acme,Engineer\n"
        )
        resp = auth_client.post(
            "/upload",
            files={"file": ("dup.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "inserted" in data
        assert data["inserted"] >= 1

    def test_upload_csv_without_url_column(self, auth_client):
        csv_content = b"company,title\nAcme,Engineer\n"
        resp = auth_client.post(
            "/upload",
            files={"file": ("bad.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 400
        data = resp.json()["detail"]
        assert data["missing_required_columns"] == ["url"]


class TestRows:
    def test_list_rows(self, auth_client):
        resp = auth_client.get("/rows")
        assert resp.status_code == 200

    def test_list_rows_with_filter(self, auth_client):
        resp = auth_client.get("/rows", params={"ats_group": "greenhouse"})
        assert resp.status_code == 200

    def test_list_rows_structure(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows")
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "columns" in data
        assert "total_count" in data
        assert "has_next" in data
        assert "filter_options" in data
        assert isinstance(data["columns"], list)
        assert len(data["columns"]) > 0

    def test_list_rows_returns_correct_total(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/rows")
        data = resp.json()
        assert data["total_count"] >= 20


class TestAnalytics:
    def test_analytics_endpoint(self, auth_client):
        resp = auth_client.get("/crm/analytics")
        assert resp.status_code == 200

    def test_funnel_analytics(self, auth_client):
        resp = auth_client.get("/crm/analytics/funnel")
        assert resp.status_code == 200

    def test_analytics_returns_all_expected_keys(self, auth_client):
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

    def test_analytics_funnel_structure(self, auth_client):
        auth_client.post("/test/seed")
        resp = auth_client.get("/crm/analytics/funnel")
        data = resp.json()
        assert "stages" in data
        assert "rates" in data
        assert isinstance(data["stages"], list)
        assert len(data["stages"]) > 0
        for stage in data["stages"]:
            assert "name" in stage
            assert "count" in stage


class TestTestEndpoints:
    def test_seed(self, client):
        resp = client.post("/test/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data

    def test_reset(self, client):
        resp = client.post("/test/reset")
        assert resp.status_code == 200
