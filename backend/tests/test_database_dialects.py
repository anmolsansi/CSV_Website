import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user
from app.database import get_db
from app.main import app
from app.models import CsvRow, User


NUMERIC_VALUES = ["2", "10", "85%", "1,000", "$99.50", "-3", "", "invalid"]
ASCENDING_VALUES = ["-3", "2", "10", "85%", "$99.50", "1,000", "invalid", ""]
DESCENDING_VALUES = ["1,000", "$99.50", "85%", "10", "2", "-3", "invalid", ""]


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
PLAYWRIGHT_CONFIG_PATH = REPOSITORY_ROOT / "frontend" / "playwright.config.ts"


def _ci_workflow_text():
    text = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert text.strip(), "CI workflow must not be empty"
    return text


def _workflow_step(text, step_name):
    marker = f"      - name: {step_name}"
    start = text.index(marker)
    end = text.find("\n      - ", start + len(marker))
    return text[start:] if end == -1 else text[start:end]


def _seed_numeric_rows(engine, marker):
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        user = User(email=f"jg020-{uuid4().hex}@example.test")
        db.add(user)
        db.flush()

        for index, score in enumerate(NUMERIC_VALUES):
            db.add(
                CsvRow(
                    user_id=user.id,
                    upload_batch_id=f"jg020-{uuid4().hex[:20]}",
                    url=f"https://example.test/jg020/{marker}/{index}",
                    company_guess=marker,
                    title=f"{marker} score {index}",
                    resume_match_score=score,
                )
            )

        db.commit()
        return user.id
    finally:
        db.close()


def _cleanup_numeric_rows(engine, user_id):
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.query(CsvRow).filter(CsvRow.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _api_sorted_scores(engine, user_id, marker, direction):
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def override_get_current_user():
        return SimpleNamespace(id=user_id)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        with TestClient(app) as client:
            response = client.get(
                "/rows",
                params={
                    "q": marker,
                    "sort_by": "resume_match_score",
                    "sort_dir": direction,
                    "page": 1,
                    "page_size": 50,
                },
            )
        assert response.status_code == 200, (
            f"{engine.dialect.name} rows API failed with "
            f"{response.status_code}: {response.text}"
        )
        payload = response.json()
        assert payload["total_count"] == len(NUMERIC_VALUES), payload
        return [row["data"]["resume_match_score"] for row in payload["rows"]]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _run_sqlite_startup_probe(database_path):
    backend_root = Path(__file__).resolve().parents[1]
    script = """
from fastapi.testclient import TestClient

from app.database import engine
from app.main import app

with engine.connect() as connection:
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    assert connection.exec_driver_sql(
        "SELECT jobgrid_numeric(?)", ("$1,000.50",)
    ).scalar_one() == 1000.5
    assert connection.exec_driver_sql(
        "SELECT jobgrid_numeric(?)", ("invalid",)
    ).scalar_one() is None

with TestClient(app) as client:
    response = client.get("/health")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}

engine.dispose()
print("JG020_STARTUP_OK")
"""
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "TEST_AUTH": "true",
            "SECRET_KEY": "jg020-startup-smoke-secret",
            "FRONTEND_URL": "http://localhost:5173",
            "ENVIRONMENT": "test",
            "RUN_MAINTENANCE_JOBS": "false",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        "SQLite application startup probe failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "JG020_STARTUP_OK" in result.stdout, result.stdout


def test_new_connection_has_function(sqlite_acceptance_engine):
    for connection_number in range(2):
        with sqlite_acceptance_engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql(
                "SELECT jobgrid_numeric(?)",
                ("$1,000.50",),
            ).scalar_one() == pytest.approx(1000.5)
            assert connection.exec_driver_sql(
                "SELECT jobgrid_numeric(?)",
                ("invalid",),
            ).scalar_one() is None

        if connection_number == 0:
            # Force the next checkout to create a new physical DBAPI connection.
            sqlite_acceptance_engine.dispose()


def test_foreign_key_fixture_enforced(sqlite_acceptance_engine):
    with pytest.raises(IntegrityError):
        with sqlite_acceptance_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO oauth_identities (user_id, provider, provider_id)
                VALUES (?, ?, ?)
                """,
                (999999, "test", "missing-user"),
            )


def test_both_dialect_api_responses_are_200(engine, sqlite_acceptance_engine):
    if engine.dialect.name != "postgresql":
        message = (
            "dual-dialect release acceptance requires DATABASE_URL to use PostgreSQL; "
            "the disposable SQLite path is covered separately"
        )
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail(message)
        pytest.skip(f"{message}; a local skip is not release evidence")

    sqlite_marker = f"JG020 SQLite {uuid4().hex}"
    postgres_marker = f"JG020 PostgreSQL {uuid4().hex}"
    sqlite_user_id = _seed_numeric_rows(sqlite_acceptance_engine, sqlite_marker)
    postgres_user_id = _seed_numeric_rows(engine, postgres_marker)

    try:
        for runtime_engine, user_id, marker in (
            (sqlite_acceptance_engine, sqlite_user_id, sqlite_marker),
            (engine, postgres_user_id, postgres_marker),
        ):
            assert _api_sorted_scores(
                runtime_engine, user_id, marker, "asc"
            ) == ASCENDING_VALUES
            assert _api_sorted_scores(
                runtime_engine, user_id, marker, "desc"
            ) == DESCENDING_VALUES
    finally:
        _cleanup_numeric_rows(sqlite_acceptance_engine, sqlite_user_id)
        _cleanup_numeric_rows(engine, postgres_user_id)


def test_startup_and_new_connection_smoke(tmp_path):
    database_path = tmp_path / "jg020-restart.sqlite3"

    # Two fresh Python interpreters against the same file simulate an application
    # restart. Each process must install the connection adapters independently.
    _run_sqlite_startup_probe(database_path)
    _run_sqlite_startup_probe(database_path)


@pytest.mark.postgresql
def test_release_requires_real_postgres_result(engine, postgres_test_url):
    assert engine.dialect.name == "postgresql", (
        "release evidence requires the ordinary backend test runtime to execute "
        "against PostgreSQL"
    )

    isolated = make_url(postgres_test_url)
    regular = make_url(str(engine.url))
    assert isolated.get_backend_name() == "postgresql"
    assert regular.get_backend_name() == "postgresql"
    assert isolated.database != regular.database

    with engine.connect() as connection:
        server_version_num = int(
            connection.exec_driver_sql("SHOW server_version_num").scalar_one()
        )

    assert server_version_num // 10000 == 16, (
        "R6 release acceptance is approved for PostgreSQL 16; "
        f"observed server_version_num={server_version_num}"
    )



def test_workflow_command_resolves_backend_directory():
    workflow = _ci_workflow_text()
    start_step = _workflow_step(workflow, "Start migrated backend server")

    assert "working-directory: ${{ github.workspace }}/backend" in start_step
    assert "python -m alembic upgrade head" in start_step
    assert "python -m uvicorn app.main:app" in start_step
    assert "cd ../backend" not in workflow


def test_health_timeout_fails_job():
    start_step = _workflow_step(
        _ci_workflow_text(), "Start migrated backend server"
    )

    assert "for attempt in $(seq 1 60)" in start_step
    assert "curl -fsS http://localhost:8000/health" in start_step
    assert 'kill -0 "$BACKEND_PID"' in start_step
    assert 'if [ "$READY" -ne 1 ]' in start_step
    assert "backend-server.log" in start_step
    assert "postgresql" in start_step and "***:***@" in start_step
    assert "exit 1" in start_step
    assert "sleep 5" not in start_step


def test_postgres_suite_and_browser_suite_run():
    workflow = _ci_workflow_text()
    playwright_config = PLAYWRIGHT_CONFIG_PATH.read_text(encoding="utf-8")

    assert workflow.count("image: postgres:16") >= 2
    assert "DATABASE_URL: postgresql+psycopg2://postgres:postgres@localhost:5432/jobgrid_test" in workflow
    assert "TEST_DATABASE_URL: postgresql+psycopg2://postgres:postgres@localhost:5432/jobgrid_schema_test" in workflow
    assert "DATABASE_URL: postgresql+psycopg2://testuser:testpass@localhost:5432/jobgrid_test" in workflow
    assert "TEST_DATABASE_URL: postgresql+psycopg2://testuser:testpass@localhost:5432/jobgrid_schema_test" in workflow
    assert "- name: Run pytest" in workflow
    assert "- name: Run E2E tests" in workflow
    assert "npx playwright test --project=chromium" in workflow
    assert "dependencies: ['setup']" in playwright_config


def test_zero_tests_or_failed_setup_is_not_success():
    workflow = _ci_workflow_text()
    backend_collection = _workflow_step(
        workflow, "Verify backend test collection is nonempty"
    )
    browser_collection = _workflow_step(
        workflow, "Verify browser test collection is nonempty"
    )
    e2e_step = _workflow_step(workflow, "Run E2E tests")
    playwright_config = PLAYWRIGHT_CONFIG_PATH.read_text(encoding="utf-8")

    assert "pytest tests/ --collect-only -q" in backend_collection
    assert "set -euo pipefail" in backend_collection
    assert "|| true" not in backend_collection

    assert "playwright test --list --project=chromium" in browser_collection
    assert "Total: [1-9][0-9]* tests?" in browser_collection
    assert "exit 1" in browser_collection
    assert "|| true" not in browser_collection

    assert "npx playwright test --project=chromium" in e2e_step
    assert "dependencies: ['setup']" in playwright_config
    assert "production" not in workflow.lower()
