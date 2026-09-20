import os
import re
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_DEFAULT_TEST_DATABASE_URL = "sqlite:///:memory:"

os.environ.setdefault("TEST_AUTH", "true")
os.environ.setdefault("DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("ENVIRONMENT", "test")

from app.database import Base, create_jobgrid_engine, get_db
from app.main import app


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "postgresql: requires an isolated TEST_DATABASE_URL and PostgreSQL runtime",
    )


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    test_db_url = os.environ.get("DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)

    if test_db_url == _DEFAULT_TEST_DATABASE_URL:
        suite_dir = tmp_path_factory.mktemp("jobgrid-suite")
        test_db_url = f"sqlite:///{suite_dir / 'suite.sqlite3'}"

    eng = create_jobgrid_engine(
        test_db_url,
        connect_args={"check_same_thread": False}
        if test_db_url.startswith("sqlite")
        else {},
    )
    if eng.dialect.name == "postgresql":
        # The ordinary test database remains separate from JG-019's dedicated
        # TEST_DATABASE_URL schema-acceptance database.
        Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)

    yield eng

    if eng.dialect.name != "postgresql":
        Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def sqlite_acceptance_engine(tmp_path, request):
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", request.node.name).strip("-")
    database_path = tmp_path / f"{safe_name or 'jg019'}.sqlite3"
    eng = create_jobgrid_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="session")
def postgres_test_url():
    """Return the isolated PostgreSQL acceptance URL.

    Local runs may omit it and skip PostgreSQL-only acceptance. Mandatory CI
    must supply it; a missing value there is a hard failure, never schema proof.
    """

    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        message = (
            "@pytest.mark.postgresql schema acceptance requires an isolated "
            "TEST_DATABASE_URL"
        )
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail(message)
        pytest.skip(f"{message}; local skip is not schema acceptance")

    try:
        parsed = make_url(test_url)
    except Exception as exc:
        pytest.fail(f"TEST_DATABASE_URL is invalid: {exc}")

    if parsed.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")

    database_name = parsed.database or ""
    if "test" not in database_name.lower():
        pytest.fail(
            "TEST_DATABASE_URL must name an explicitly disposable test database"
        )

    regular_url = os.environ.get("DATABASE_URL")
    if regular_url:
        regular = make_url(regular_url)
        same_target = (
            regular.get_backend_name() == "postgresql"
            and regular.host == parsed.host
            and regular.port == parsed.port
            and regular.database == parsed.database
        )
        if same_target:
            pytest.fail(
                "TEST_DATABASE_URL must target a database distinct from DATABASE_URL"
            )

    return test_url


@pytest.fixture()
def db_session(engine):
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(engine):
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(client):
    resp = client.post("/auth/dev-login", json={"email": "test@jobgrid.dev"})
    assert resp.status_code == 200
    return client
