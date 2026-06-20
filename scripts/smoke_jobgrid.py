#!/usr/bin/env python3
"""Smoke tests for JobGrid API endpoints.

Usage:
    python scripts/smoke_jobgrid.py [--base-url URL] [--cookie COOKIE]

Requires: requests (pip install requests)
"""
import argparse
import csv
import io
import json
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)


class SmokeTest:
    def __init__(self, base_url: str, cookie: str | None = None):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        if cookie:
            self.session.headers["Cookie"] = cookie
        self.results: list[dict] = []
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
        self._test("GET /auth/me", self.test_auth_me)
        self._test("POST /upload (CSV)", self.test_upload)
        self._test("GET /rows", self.test_list_rows)
        self._test("POST /rows/{id}/click", self.test_record_click)
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
        r = self.session.get(f"{self.base}/health", timeout=10)
        r.raise_for_status()
        data = r.json()
        assert data.get("status") == "ok", f"Expected status=ok, got {data}"
        return "ok"

    def test_auth_me(self):
        r = self.session.get(f"{self.base}/auth/me", timeout=10)
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
        writer.writerow(["https://example.com/job/1", "Software Engineer", "ExampleCorp", "greenhouse", "backend", "85"])
        writer.writerow(["https://example.com/job/2", "Data Scientist", "DataInc", "lever", "data", "72"])
        writer.writerow(["https://example.com/job/3", "Frontend Dev", "WebCo", "ashby", "frontend", "90"])
        buf.seek(0)

        files = {"file": ("test_jobs.csv", buf.getvalue().encode(), "text/csv")}
        r = self.session.post(f"{self.base}/upload", files=files, timeout=30)
        r.raise_for_status()
        data = r.json()
        assert "rows_inserted" in data or "inserted" in data or "total" in data, f"Unexpected: {data}"
        return f"inserted={data.get('rows_inserted', data.get('inserted', '?'))}"

    def test_list_rows(self):
        r = self.session.get(f"{self.base}/rows?sort_by=created_at&sort_dir=desc", timeout=15)
        r.raise_for_status()
        data = r.json()
        assert "rows" in data, f"Missing 'rows' key: {data}"
        if data["rows"]:
            self.row_id = data["rows"][0]["id"]
        return f"count={len(data['rows'])}"

    def test_record_click(self):
        if not self.row_id:
            raise Exception("No row_id available from previous test")
        r = self.session.post(f"{self.base}/rows/{self.row_id}/click", timeout=10)
        r.raise_for_status()
        data = r.json()
        assert data.get("clicked") is True, f"Expected clicked=True, got {data}"
        return f"row={self.row_id}"

    def test_get_preferences(self):
        r = self.session.get(f"{self.base}/preferences", timeout=10)
        r.raise_for_status()
        data = r.json()
        assert "hidden_columns" in data, f"Unexpected: {data}"
        return "ok"

    def test_set_preferences(self):
        payload = {"hidden_columns": ["clearance_matches"], "column_order": []}
        r = self.session.put(f"{self.base}/preferences", json=payload, timeout=10)
        r.raise_for_status()
        return "ok"

    def test_create_app_from_row(self):
        if not self.row_id:
            raise Exception("No row_id available")
        r = self.session.post(f"{self.base}/crm/from-row/{self.row_id}", timeout=10)
        r.raise_for_status()
        data = r.json()
        self.app_id = data.get("id")
        assert "status" in data, f"Unexpected: {data}"
        return f"app_id={self.app_id}"

    def test_bulk_create_from_rows(self):
        if not self.row_id:
            raise Exception("No row_id available")
        r = self.session.post(f"{self.base}/crm/from-rows/bulk", json={"row_ids": [self.row_id]}, timeout=10)
        r.raise_for_status()
        data = r.json()
        return f"created={data.get('created', 0)}, updated={data.get('updated', 0)}"

    def test_list_applications(self):
        r = self.session.get(f"{self.base}/crm/applications?sort_by=opened_at&sort_dir=desc", timeout=15)
        r.raise_for_status()
        data = r.json()
        assert "rows" in data, f"Missing 'rows' key: {data}"
        if data["rows"] and not self.app_id:
            self.app_id = data["rows"][0]["id"]
        return f"count={len(data['rows'])}"

    def test_update_application(self):
        if not self.app_id:
            raise Exception("No app_id available")
        r = self.session.patch(f"{self.base}/crm/applications/{self.app_id}", json={"notes": "smoke test note"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        assert data.get("notes") == "smoke test note", f"Unexpected: {data}"
        return f"app={self.app_id}"

    def test_bulk_update(self):
        if not self.app_id:
            raise Exception("No app_id available")
        r = self.session.patch(f"{self.base}/crm/applications/bulk", json={"ids": [self.app_id], "patch": {"notes": "bulk updated"}}, timeout=10)
        r.raise_for_status()
        return f"updated={r.json().get('updated', 0)}"

    def test_follow_up_preset(self):
        if not self.app_id:
            raise Exception("No app_id available")
        r = self.session.post(f"{self.base}/crm/applications/{self.app_id}/follow-up?preset=7_days", timeout=10)
        r.raise_for_status()
        data = r.json()
        assert data.get("follow_up_at"), f"Expected follow_up_at to be set: {data}"
        return f"follow_up_at={data['follow_up_at']}"

    def test_stats(self):
        r = self.session.get(f"{self.base}/crm/stats", timeout=10)
        r.raise_for_status()
        data = r.json()
        assert "total_opened" in data, f"Unexpected: {data}"
        return f"opened={data['total_opened']}, applied={data['total_applied']}"

    def test_analytics(self):
        r = self.session.get(f"{self.base}/crm/analytics", timeout=15)
        r.raise_for_status()
        data = r.json()
        assert "total_urls" in data, f"Unexpected: {data}"
        return f"urls={data['total_urls']}, opened={data['total_opened']}"

    def test_create_session(self):
        r = self.session.post(f"{self.base}/crm/sessions", json={"name": "Smoke test session"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        self.session_id = data.get("id")
        return f"session_id={self.session_id}"

    def test_list_sessions(self):
        r = self.session.get(f"{self.base}/crm/sessions", timeout=10)
        r.raise_for_status()
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        return f"count={len(data)}"

    def test_list_views(self):
        r = self.session.get(f"{self.base}/crm/views", timeout=10)
        r.raise_for_status()
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        return f"count={len(data)}"

    def test_create_view(self):
        payload = {"name": "Smoke Test View", "view_type": "job_links", "filters": {"q": "test"}}
        r = self.session.post(f"{self.base}/crm/views", json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        self.view_id = data.get("id")
        return f"view_id={self.view_id}"

    def test_export_dashboard(self):
        r = self.session.get(f"{self.base}/crm/export/dashboard?format=csv", timeout=15, stream=True)
        r.raise_for_status()
        content = r.content
        return f"size={len(content)} bytes"

    def test_export_applications(self):
        r = self.session.get(f"{self.base}/crm/export/applications?format=json", timeout=15)
        r.raise_for_status()
        return f"size={len(r.content)} bytes"


def main():
    parser = argparse.ArgumentParser(description="JobGrid API smoke tests")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend URL")
    parser.add_argument("--cookie", default=None, help="Auth cookie value")
    args = parser.parse_args()

    test = SmokeTest(args.base_url, args.cookie)
    success = test.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
