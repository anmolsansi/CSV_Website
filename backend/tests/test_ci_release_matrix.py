from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SQLITE_WORKFLOW = ROOT / ".github" / "workflows" / "c07-sqlite.yml"
TIMEZONE_WORKFLOW = ROOT / ".github" / "workflows" / "c06-browser-timezones.yml"
JUNIT_VERIFIER = ROOT / "scripts" / "verify_junit.py"


def _text(path: Path) -> str:
    value = path.read_text(encoding="utf-8")
    assert value.strip(), f"{path} must not be empty"
    return value


def test_postgres_release_ci_isolated_and_explicit():
    workflow = _text(CI_WORKFLOW)

    assert "image: postgres:16" in workflow
    assert "jobgrid_test" in workflow
    assert "jobgrid_schema_test" in workflow
    assert "CORS_ORIGINS: http://localhost:5173" in workflow
    assert 'RUN_MAINTENANCE_JOBS: "false"' in workflow
    assert 'RUN_REMINDER_WORKER: "false"' in workflow
    assert 'REMINDER_EMAIL_DELIVERY_ENABLED: "false"' in workflow
    assert 'JOB_URL_CHECKS_ENABLED: "false"' in workflow
    assert "DOCUMENT_STORAGE_DIR: /tmp/jobgrid-private-documents" in workflow
    assert "python -m alembic upgrade head" in workflow
    assert "Verify C-07 backend regression collection is nonempty" in workflow
    assert "c07-backend-regressions.xml" in workflow
    assert "verify_junit.py" in workflow


def test_frontend_build_and_e2e_pin_intended_api_configuration():
    workflow = _text(CI_WORKFLOW)

    assert "VITE_API_URL: /api" in workflow
    assert 'VITE_ENABLE_DEV_LOGIN: "false"' in workflow
    assert "VITE_API_URL: http://localhost:8000" in workflow
    assert 'VITE_ENABLE_DEV_LOGIN: "true"' in workflow
    assert "Run tab-helper safety regressions" in workflow
    assert "Run JG-023 browser release workflow" in workflow
    assert "Run E2E tests" in workflow


def test_sqlite_release_job_is_nonempty_and_rejects_runtime_skips():
    workflow = _text(SQLITE_WORKFLOW)

    assert "name: Backend Tests (SQLite)" in workflow
    assert "sqlite:////tmp/jobgrid-c07-release.sqlite3" in workflow
    assert "TEST_DATABASE_URL" not in workflow
    assert 'RUN_REMINDER_WORKER: "false"' in workflow
    assert 'REMINDER_EMAIL_DELIVERY_ENABLED: "false"' in workflow
    assert "Verify PostgreSQL-only exclusions are nonempty" in workflow
    assert "Verify SQLite collection is nonempty" in workflow
    assert 'pytest tests/ -m "not postgresql"' in workflow
    assert "--max-skips 0" in workflow
    assert "sqlite-release.xml" in workflow
    assert "source_sha=" in workflow


def test_timezone_release_job_covers_all_declared_zones_and_evidence():
    workflow = _text(TIMEZONE_WORKFLOW)

    for project in ("chromium", "chromium-kolkata", "chromium-new-york"):
        assert project in workflow
    assert "CORS_ORIGINS: http://localhost:5173" in workflow
    assert 'RUN_REMINDER_WORKER: "false"' in workflow
    assert "migration_revision=" in workflow
    assert "source_sha=" in workflow
    assert "Sanitize C-06 backend logs on failure" in workflow
    assert "playwright-report/" in workflow
    assert "test-results/" in workflow


def test_junit_verifier_rejects_empty_and_skipped_reports(tmp_path):
    passing = tmp_path / "passing.xml"
    passing.write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0"></testsuite>',
        encoding="utf-8",
    )
    empty = tmp_path / "empty.xml"
    empty.write_text(
        '<testsuite tests="0" failures="0" errors="0" skipped="0"></testsuite>',
        encoding="utf-8",
    )
    skipped = tmp_path / "skipped.xml"
    skipped.write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="1"></testsuite>',
        encoding="utf-8",
    )

    ok = subprocess.run(
        [sys.executable, str(JUNIT_VERIFIER), str(passing)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0, ok.stderr

    no_tests = subprocess.run(
        [sys.executable, str(JUNIT_VERIFIER), str(empty)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert no_tests.returncode != 0
    assert "expected at least 1 tests" in (no_tests.stdout + no_tests.stderr)

    unexpected_skip = subprocess.run(
        [sys.executable, str(JUNIT_VERIFIER), str(skipped), "--max-skips", "0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert unexpected_skip.returncode != 0
    assert "exceeds allowed 0" in (unexpected_skip.stdout + unexpected_skip.stderr)
