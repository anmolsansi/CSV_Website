#!/usr/bin/env python3
"""Smoke tests for JobGrid API endpoints.

Usage:
    python scripts/smoke_jobgrid.py [--base-url URL] [--cookie COOKIE] [--no-dev-login]

Requires backend dependencies from backend/requirements.txt.
"""
import argparse
import csv
import io
import json
import sys
import time
from datetime import datetime, timedelta, timezone

try:
    import httpx
except ImportError:
    print("ERROR: 'httpx' not installed. Run: cd backend && python -m pip install -r requirements.txt")
    sys.exit(1)


class SmokeTest:
    def __init__(self, base_url: str, cookie: str | None = None, dev_login: bool = True, email: str = "test@jobgrid.dev"):
        self.base = base_url.rstrip("/")
        self.session = httpx.Client(timeout=30)
        if cookie:
            self.session.headers["Cookie"] = cookie
        self.dev_login = dev_login and not cookie
        self.email = email
        self.run_id = f"smoke-{int(time.time())}"
        self.results: list[dict] = []
        self.row_ids: list[int] = []
        self.row_id: int | None = None
        self.app_id: int | None = None
        self.session_id: int | None = None
        self.view_id: int | None = None
        self.batch_id: int | None = None

    def _test(self, name: str, fn):
        try:
            result = fn()
            self.results.append({"name": name, "status": "PASS", "detail": result})
            print(f"  PASS  {name}")
        except Exception as e:
            self.results.append({"name": name, "status": "FAIL", "detail": str(e)})
            print(f"  FAIL  {name}: {e}")

    def run(self):
        print(f"\n{'='*60}")
        print(f"JobGrid Smoke Tests — {self.base}")
        print(f"{'='*60}\n")

        self._test("GET /health", self.test_health)
        if self.dev_login:
            self._test("POST /auth/dev-login", self.test_dev_login)
        self._test("GET /auth/me", self.test_auth_me)
        self._test("POST /upload (CSV)", self.test_upload)
        self._test("GET /rows", self.test_list_rows)
        self._test("POST /rows/{id}/click", self.test_record_click)
        self._test("GET /rows confirms clicked row", self.test_clicked_row_visible)
        self._test("GET /preferences", self.test_get_preferences)
        self._test("PUT /preferences", self.test_set_preferences)
        self._test("POST /crm/from-row/{id}", self.test_create_app_from_row)
        self._test("POST /crm/from-rows/bulk", self.test_bulk_create_from_rows)
        self._test("GET /crm/applications", self.test_list_applications)
        self._test("PATCH /crm/applications/{id}", self.test_update_application)
        self._test("PATCH /crm/applications/bulk", self.test_bulk_update)
        self._test("POST /crm/applications/{id}/follow-up", self.test_follow_up_preset)
        self._test("GET /crm/stats", self.test_stats)
        self._test("GET /crm/analytics", self.test_analytics)
        self._test("POST /crm/sessions", self.test_create_session)
        self._test("GET /crm/sessions", self.test_list_sessions)
        self._test("GET /crm/views", self.test_list_views)
        self._test("POST /crm/views", self.test_create_view)
        self._test("GET /crm/export/dashboard", self.test_export_dashboard)
        self._test("GET /crm/export/applications", self.test_export_applications)

        print(f"\n{'='*60}")
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        print(f"Results: {passed} passed, {failed} failed, {len(self.results)} total")
        print(f"{'='*60}\n")

        return failed == 0

    def test_health(self):
        r = self.session.get(f"{self.base}/health")
        r.raise_for_status()
        data = r.json()
        assert data.get("status") == "ok", f"Expected status=ok, got {data}"
        return "ok"

    def test_dev_login(self):
        r = self.session.post(f"{self.base}/auth/dev-login", json={"email": self.email})
        r.raise_for_status()
        data = r.json()
        assert data.get("email") == self.email, f"Unexpected dev login response: {data}"
        return f"user={data['email']}"

    def test_auth_me(self):
        r = self.session.get(f"{self.base}/auth/me")
        if r.status_code == 401:
            return "No auth (expected in test mode)"
        r.raise_for_status()
        data = r.json()
        assert "id" in data or "email" in data, f"Unexpected response: {data}"
        return f"user={data.get('email', 'unknown')}"

    def test_upload(self):
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["url", "title", "company_guess", "ats_group", "search_bucket", "resume_match_score"])
        writer.writerow([f"https://{self.run_id}.example.com/job/1", "Software Engineer", "ExampleCorp", "greenhouse", "backend", "85"])
        writer.writerow([f"https://{self.run_id}.example.com/job/2", "Data Scientist", "DataInc", "lever", "data", "72"])
        writer.writerow([f"https://{self.run_id}.example.com/job/3", "Frontend Dev", "WebCo", "ashby", "frontend", "90"])
        buf.seek(0)

        files = {"file": ("test_jobs.csv", buf.getvalue().encode(), "text/csv")}
        r = self.session.post(f"{self.base}/upload", files=files)
        r.raise_for_status()
        data = r.json()
        assert "rows_inserted" in data or "inserted" in data or "total" in data, f"Unexpected: {data}"
        assert data.get("inserted", data.get("rows_inserted", 0)) >= 3, f"Expected new rows for run {self.run_id}: {data}"
        return f"inserted={data.get('rows_inserted', data.get('inserted', '?'))}"

    def test_list_rows(self):
        r = self.session.get(f"{self.base}/rows", params={"sort_by": "created_at", "sort_dir": "desc", "q": self.run_id})
        r.raise_for_status()
        data = r.json()
        assert "rows" in data, f"Missing 'rows' key: {data}"
        assert len(data["rows"]) >= 3, f"Expected uploaded smoke rows, got {data}"
        self.row_ids = [row["id"] for row in data["rows"]]
        self.row_id = self.row_ids[0]
        return f"count={len(data['rows'])}"

    def test_record_click(self):
        if not self.row_id:
            raise Exception("No row_id available from previous test")
        r = self.session.post(f"{self.base}/rows/{self.row_id}/click")
        r.raise_for_status()
        data = r.json()
        assert data.get("clicked") is True, f"Expected clicked=True, got {data}"
        return f"row={self.row_id}"

    def test_clicked_row_visible(self):
        if not self.row_id:
            raise Exception("No row_id available from previous test")
        r = self.session.get(f"{self.base}/rows", params={"q": self.run_id})
        r.raise_for_status()
        data = r.json()
        row = next((item for item in data["rows"] if item["id"] == self.row_id), None)
        assert row, f"Clicked row {self.row_id} not returned"
        assert row.get("clicked") is True, f"Expected clicked row to stay green/visited: {row}"
        return f"row={self.row_id} clicked"

    def test_get_preferences(self):
        r = self.session.get(f"{self.base}/preferences")
        r.raise_for_status()
        data = r.json()
        assert "hidden_columns" in data, f"Unexpected: {data}"
        return "ok"

    def test_set_preferences(self):
        payload = {"hidden_columns": ["clearance_matches"], "column_order": []}
        r = self.session.put(f"{self.base}/preferences", json=payload)
        r.raise_for_status()
        return "ok"

    def test_create_app_from_row(self):
        if not self.row_id:
            raise Exception("No row_id available")
        r = self.session.post(f"{self.base}/crm/from-row/{self.row_id}")
        r.raise_for_status()
        data = r.json()
        self.app_id = data.get("id")
        assert "status" in data, f"Unexpected: {data}"
        return f"app_id={self.app_id}"

    def test_bulk_create_from_rows(self):
        if not self.row_id:
            raise Exception("No row_id available")
        row_ids = self.row_ids or [self.row_id]
        r = self.session.post(f"{self.base}/crm/from-rows/bulk", json={"row_ids": row_ids})
        r.raise_for_status()
        data = r.json()
        return f"created={data.get('created', 0)}, updated={data.get('updated', 0)}"

    def test_list_applications(self):
        r = self.session.get(f"{self.base}/crm/applications", params={"sort_by": "opened_at", "sort_dir": "desc", "q": self.run_id})
        r.raise_for_status()
        data = r.json()
        assert "rows" in data, f"Missing 'rows' key: {data}"
        assert data["rows"], f"Expected applications for uploaded rows: {data}"
        if data["rows"] and not self.app_id:
            self.app_id = data["rows"][0]["id"]
        return f"count={len(data['rows'])}"

    def test_update_application(self):
        if not self.app_id:
            raise Exception("No app_id available")
        follow_up_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        r = self.session.patch(
            f"{self.base}/crm/applications/{self.app_id}",
            json={"status": "follow_up", "follow_up_at": follow_up_at, "notes": "smoke test note"},
        )
        r.raise_for_status()
        data = r.json()
        assert data.get("notes") == "smoke test note", f"Unexpected: {data}"
        assert data.get("status") == "follow_up", f"Unexpected status update: {data}"
        assert data.get("follow_up_at"), f"Expected follow_up_at update: {data}"
        return f"app={self.app_id}"

    def test_bulk_update(self):
        if not self.app_id:
            raise Exception("No app_id available")
        r = self.session.patch(f"{self.base}/crm/applications/bulk", json={"ids": [self.app_id], "patch": {"notes": "bulk updated"}})
        r.raise_for_status()
        return f"updated={r.json().get('updated', 0)}"

    def test_follow_up_preset(self):
        if not self.app_id:
            raise Exception("No app_id available")
        r = self.session.post(f"{self.base}/crm/applications/{self.app_id}/follow-up?preset=7_days")
        r.raise_for_status()
        data = r.json()
        assert data.get("follow_up_at"), f"Expected follow_up_at to be set: {data}"
        return f"follow_up_at={data['follow_up_at']}"

    def test_stats(self):
        r = self.session.get(f"{self.base}/crm/stats")
        r.raise_for_status()
        data = r.json()
        assert "total_opened" in data, f"Unexpected: {data}"
        return f"opened={data['total_opened']}, applied={data['total_applied']}"

    def test_analytics(self):
        r = self.session.get(f"{self.base}/crm/analytics")
        r.raise_for_status()
        data = r.json()
        assert "total_urls" in data, f"Unexpected: {data}"
        return f"urls={data['total_urls']}, opened={data['total_opened']}"

    def test_create_session(self):
        r = self.session.post(f"{self.base}/crm/sessions", json={"name": f"Smoke test session {self.run_id}"})
        r.raise_for_status()
        data = r.json()
        self.session_id = data.get("id")
        return f"session_id={self.session_id}"

    def test_list_sessions(self):
        r = self.session.get(f"{self.base}/crm/sessions")
        r.raise_for_status()
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        return f"count={len(data)}"

    def test_list_views(self):
        r = self.session.get(f"{self.base}/crm/views")
        r.raise_for_status()
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        return f"count={len(data)}"

    def test_create_view(self):
        payload = {"name": f"Smoke Test View {self.run_id}", "view_type": "job_links", "filters": {"q": self.run_id}}
        r = self.session.post(f"{self.base}/crm/views", json=payload)
        r.raise_for_status()
        data = r.json()
        self.view_id = data.get("id")
        return f"view_id={self.view_id}"

    def test_export_dashboard(self):
        r = self.session.get(f"{self.base}/crm/export/dashboard?format=csv")
        r.raise_for_status()
        content = r.content
        return f"size={len(content)} bytes"

    def test_export_applications(self):
        r = self.session.get(f"{self.base}/crm/export/applications?format=json")
        r.raise_for_status()
        return f"size={len(r.content)} bytes"


def main():
    parser = argparse.ArgumentParser(description="JobGrid API smoke tests")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend URL")
    parser.add_argument("--cookie", default=None, help="Auth cookie value")
    parser.add_argument("--no-dev-login", action="store_true", help="Do not call /auth/dev-login before smoke tests")
    parser.add_argument("--email", default="test@jobgrid.dev", help="Email used with --dev-login")
    args = parser.parse_args()

    test = SmokeTest(args.base_url, args.cookie, dev_login=not args.no_dev_login, email=args.email)
    success = test.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
