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



RELEASE_GATE_NAMES = (
    "staging_restore_content_comparison",
    "oauth_real_provider_not_dev_login",
    "smtp_received_not_merely_queued",
    "rollback_preserves_user_history",
    "deployment_smoke_and_rollback",
)
ALLOWED_RELEASE_GATE_STATUSES = {"PASS", "FAIL", "BLOCKED"}


def _release_require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _validate_release_gate_common(name: str, gate: dict) -> str:
    _release_require(isinstance(gate, dict), f"{name}: gate must be an object")
    status = str(gate.get("status", "")).upper()
    _release_require(
        status in ALLOWED_RELEASE_GATE_STATUSES,
        f"{name}: status must be PASS, FAIL, or BLOCKED",
    )
    for field in ("owner", "environment", "command", "expected", "actual"):
        _release_require(
            isinstance(gate.get(field), str) and gate[field].strip(),
            f"{name}: {field} is required",
        )
    if status == "BLOCKED":
        _release_require(
            isinstance(gate.get("blocker"), str) and gate["blocker"].strip(),
            f"{name}: BLOCKED requires an exact blocker",
        )
    return status


def staging_restore_content_comparison(gate: dict):
    status = _validate_release_gate_common("staging_restore_content_comparison", gate)
    if status != "PASS":
        return status

    source_count = gate.get("source_count")
    restored_count = gate.get("restored_count")
    _release_require(
        isinstance(source_count, int) and source_count > 0,
        "staging_restore_content_comparison: source_count must be nonzero",
    )
    _release_require(
        restored_count == source_count,
        "staging_restore_content_comparison: restored_count must equal source_count",
    )
    source_hash = gate.get("source_content_sha256")
    restored_hash = gate.get("restored_content_sha256")
    _release_require(
        _is_sha256(source_hash) and _is_sha256(restored_hash),
        "staging_restore_content_comparison: both content hashes must be SHA-256",
    )
    _release_require(
        source_hash.lower() == restored_hash.lower(),
        "staging_restore_content_comparison: restored content hash differs from source",
    )
    _release_require(
        _is_sha256(gate.get("backup_sha256")),
        "staging_restore_content_comparison: backup_sha256 must be recorded",
    )
    return status


def oauth_real_provider_not_dev_login(gate: dict):
    status = _validate_release_gate_common("oauth_real_provider_not_dev_login", gate)
    if status != "PASS":
        return status

    provider = str(gate.get("provider", "")).strip().lower()
    _release_require(
        provider in {"google", "microsoft", "apple"},
        "oauth_real_provider_not_dev_login: provider must be google, microsoft, or apple",
    )
    _release_require(
        gate.get("used_dev_login") is False,
        "oauth_real_provider_not_dev_login: dev-login evidence is not provider acceptance",
    )
    _release_require(
        gate.get("auth_me_status") == 200,
        "oauth_real_provider_not_dev_login: /auth/me must return 200 after callback",
    )
    _release_require(
        gate.get("logout_status") in {302, 303},
        "oauth_real_provider_not_dev_login: logout must redirect",
    )
    _release_require(
        gate.get("logout_cleared_cookie") is True,
        "oauth_real_provider_not_dev_login: logout must clear session_token",
    )
    _release_require(
        gate.get("session_cookie_secure") is True,
        "oauth_real_provider_not_dev_login: production session cookie must be Secure",
    )
    _release_require(
        str(gate.get("session_cookie_samesite", "")).lower() == "none",
        "oauth_real_provider_not_dev_login: production session cookie must use SameSite=None",
    )
    return status


def smtp_received_not_merely_queued(gate: dict):
    status = _validate_release_gate_common("smtp_received_not_merely_queued", gate)
    if status != "PASS":
        return status

    _release_require(
        str(gate.get("api_status", "")).lower() == "sent",
        "smtp_received_not_merely_queued: logged/queued-only status is not delivery evidence",
    )
    _release_require(
        gate.get("recipient_controlled") is True,
        "smtp_received_not_merely_queued: recipient must be a controlled sandbox",
    )
    _release_require(
        gate.get("received") is True,
        "smtp_received_not_merely_queued: sandbox must confirm receipt",
    )
    _release_require(
        isinstance(gate.get("received_message_id"), str)
        and gate["received_message_id"].strip(),
        "smtp_received_not_merely_queued: received_message_id is required",
    )
    _release_require(
        _is_sha256(gate.get("received_subject_sha256")),
        "smtp_received_not_merely_queued: received subject hash is required",
    )
    _release_require(
        _is_sha256(gate.get("received_body_sha256")),
        "smtp_received_not_merely_queued: received body hash is required",
    )
    return status


def rollback_preserves_user_history(gate: dict):
    status = _validate_release_gate_common("rollback_preserves_user_history", gate)
    if status != "PASS":
        return status

    before_count = gate.get("before_history_count")
    after_count = gate.get("after_history_count")
    _release_require(
        isinstance(before_count, int) and before_count > 0,
        "rollback_preserves_user_history: before_history_count must be nonzero",
    )
    _release_require(
        after_count == before_count,
        "rollback_preserves_user_history: history count changed during rollback rehearsal",
    )
    before_hash = gate.get("before_history_sha256")
    after_hash = gate.get("after_history_sha256")
    _release_require(
        _is_sha256(before_hash) and _is_sha256(after_hash),
        "rollback_preserves_user_history: before/after hashes must be SHA-256",
    )
    _release_require(
        before_hash.lower() == after_hash.lower(),
        "rollback_preserves_user_history: user-history content changed",
    )
    for field in ("old_code_started", "new_columns_retained", "current_code_restored"):
        _release_require(
            gate.get(field) is True,
            f"rollback_preserves_user_history: {field} must be true",
        )
    return status


def deployment_smoke_and_rollback(gate: dict):
    status = _validate_release_gate_common("deployment_smoke_and_rollback", gate)
    if status != "PASS":
        return status

    _release_require(
        gate.get("backend_health_status") == 200,
        "deployment_smoke_and_rollback: backend /health must return 200",
    )
    _release_require(
        gate.get("frontend_status") == 200,
        "deployment_smoke_and_rollback: frontend root must return 200",
    )
    for field in ("rollback_trigger", "rollback_command"):
        _release_require(
            isinstance(gate.get(field), str) and gate[field].strip(),
            f"deployment_smoke_and_rollback: {field} is required",
        )
    return status


RELEASE_GATE_VALIDATORS = {
    "staging_restore_content_comparison": staging_restore_content_comparison,
    "oauth_real_provider_not_dev_login": oauth_real_provider_not_dev_login,
    "smtp_received_not_merely_queued": smtp_received_not_merely_queued,
    "rollback_preserves_user_history": rollback_preserves_user_history,
    "deployment_smoke_and_rollback": deployment_smoke_and_rollback,
}


def validate_release_evidence(payload: dict) -> dict:
    _release_require(isinstance(payload, dict), "release evidence must be a JSON object")
    candidate = payload.get("release_candidate")
    _release_require(
        isinstance(candidate, dict),
        "release_candidate object is required",
    )
    for field in ("source_sha", "environment", "owner"):
        _release_require(
            isinstance(candidate.get(field), str) and candidate[field].strip(),
            f"release_candidate.{field} is required",
        )

    gates = payload.get("gates")
    _release_require(isinstance(gates, dict), "gates object is required")

    statuses = {}
    for name in RELEASE_GATE_NAMES:
        _release_require(name in gates, f"missing release gate: {name}")
        statuses[name] = RELEASE_GATE_VALIDATORS[name](gates[name])

    staging_accepted = all(status == "PASS" for status in statuses.values())
    blocked = [name for name, status in statuses.items() if status == "BLOCKED"]
    failed = [name for name, status in statuses.items() if status == "FAIL"]

    return {
        "source_sha": candidate["source_sha"],
        "environment": candidate["environment"],
        "gates": statuses,
        "blocked": blocked,
        "failed": failed,
        "staging_accepted": staging_accepted,
        "released": False,
    }


def load_release_evidence(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return validate_release_evidence(payload)


def run_release_acceptance_self_tests() -> bool:
    sha_a = "a" * 64
    sha_b = "b" * 64
    common = {
        "status": "PASS",
        "owner": "release-owner",
        "environment": "synthetic",
        "command": "synthetic regression",
        "expected": "contract passes",
        "actual": "contract passed",
    }
    cases = {
        "staging_restore_content_comparison": {
            **common,
            "source_count": 7,
            "restored_count": 7,
            "source_content_sha256": sha_a,
            "restored_content_sha256": sha_a,
            "backup_sha256": sha_b,
        },
        "oauth_real_provider_not_dev_login": {
            **common,
            "provider": "google",
            "used_dev_login": False,
            "auth_me_status": 200,
            "logout_status": 303,
            "logout_cleared_cookie": True,
            "session_cookie_secure": True,
            "session_cookie_samesite": "none",
        },
        "smtp_received_not_merely_queued": {
            **common,
            "api_status": "sent",
            "recipient_controlled": True,
            "received": True,
            "received_message_id": "sandbox-message-1",
            "received_subject_sha256": sha_a,
            "received_body_sha256": sha_b,
        },
        "rollback_preserves_user_history": {
            **common,
            "before_history_count": 5,
            "after_history_count": 5,
            "before_history_sha256": sha_a,
            "after_history_sha256": sha_a,
            "old_code_started": True,
            "new_columns_retained": True,
            "current_code_restored": True,
        },
        "deployment_smoke_and_rollback": {
            **common,
            "backend_health_status": 200,
            "frontend_status": 200,
            "rollback_trigger": "health or smoke failure",
            "rollback_command": "deploy previous application revision",
        },
    }

    for name, gate in cases.items():
        RELEASE_GATE_VALIDATORS[name](gate)
        print(f"  PASS  {name}")

    bad_oauth = dict(cases["oauth_real_provider_not_dev_login"])
    bad_oauth["used_dev_login"] = True
    try:
        oauth_real_provider_not_dev_login(bad_oauth)
    except AssertionError:
        print("  PASS  oauth regression rejects dev-login evidence")
    else:
        raise AssertionError("oauth regression accepted dev-login evidence")

    bad_smtp = dict(cases["smtp_received_not_merely_queued"])
    bad_smtp["api_status"] = "logged"
    try:
        smtp_received_not_merely_queued(bad_smtp)
    except AssertionError:
        print("  PASS  smtp regression rejects logged-only evidence")
    else:
        raise AssertionError("smtp regression accepted logged-only evidence")

    blocked = {
        name: {
            "status": "BLOCKED",
            "owner": "release-owner",
            "environment": "staging",
            "command": "not executed",
            "expected": "authorized external acceptance",
            "actual": "not executed",
            "blocker": "staging credential or authorized external resource unavailable",
        }
        for name in RELEASE_GATE_NAMES
    }
    summary = validate_release_evidence(
        {
            "release_candidate": {
                "source_sha": "synthetic",
                "environment": "staging",
                "owner": "release-owner",
            },
            "gates": blocked,
        }
    )
    _release_require(
        summary["staging_accepted"] is False and summary["released"] is False,
        "blocked gates must never become staging-accepted or released",
    )
    print("  PASS  blocked external gates remain non-accepted")
    return True

def main():
    parser = argparse.ArgumentParser(description="JobGrid API smoke and release-acceptance checks")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend URL")
    parser.add_argument("--cookie", default=None, help="Auth cookie value")
    parser.add_argument("--no-dev-login", action="store_true", help="Do not call /auth/dev-login before smoke tests")
    parser.add_argument("--email", default="test@jobgrid.dev", help="Email used with dev-login smoke mode")
    parser.add_argument(
        "--release-evidence",
        help="Validate a JG-024 release-acceptance evidence JSON file instead of running API smoke tests",
    )
    parser.add_argument(
        "--self-test-release-acceptance",
        action="store_true",
        help="Run synthetic regressions for the JG-024 acceptance evidence validators",
    )
    args = parser.parse_args()

    if args.self_test_release_acceptance:
        try:
            success = run_release_acceptance_self_tests()
        except Exception as exc:
            print(f"Release acceptance self-test failed: {exc}")
            sys.exit(1)
        sys.exit(0 if success else 1)

    if args.release_evidence:
        try:
            summary = load_release_evidence(args.release_evidence)
        except Exception as exc:
            print(f"Release evidence rejected: {exc}")
            sys.exit(1)
        print(json.dumps(summary, indent=2, sort_keys=True))
        sys.exit(1 if summary["failed"] else 0)

    test = SmokeTest(args.base_url, args.cookie, dev_login=not args.no_dev_login, email=args.email)
    success = test.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
