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


class TestRows:
    def test_list_rows(self, auth_client):
        resp = auth_client.get("/rows")
        assert resp.status_code == 200

    def test_list_rows_with_filter(self, auth_client):
        resp = auth_client.get("/rows", params={"ats_group": "greenhouse"})
        assert resp.status_code == 200


class TestAnalytics:
    def test_analytics_endpoint(self, auth_client):
        resp = auth_client.get("/crm/analytics")
        assert resp.status_code == 200

    def test_funnel_analytics(self, auth_client):
        resp = auth_client.get("/crm/analytics/funnel")
        assert resp.status_code == 200


class TestTestEndpoints:
    def test_seed(self, client):
        resp = client.post("/test/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data

    def test_reset(self, client):
        resp = client.post("/test/reset")
        assert resp.status_code == 200
